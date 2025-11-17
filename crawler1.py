import re
import time
import os
from urllib.parse import urlparse, urlunparse
import requests


def replace_timestamp_in_url(url: str, new_ts: int) -> str:
    """
    直接将 url 中的 {ts} 替换为 new_ts。
    """
    return url.replace("{ts}", str(new_ts))


def is_image_response(resp: requests.Response) -> bool:
    """
    判断响应是否是可用的图片：
    - 状态码 200
    - Content-Type 包含 'image'
    - 内容长度不为零（或至少大于阈值）
    """
    if resp.status_code != 200:
        return False
    ctype = resp.headers.get("Content-Type", "")
    if "image" not in ctype.lower():
        # 有些站点会返回 application/octet-stream，但实际是图片；可放宽判断
        if "octet-stream" not in ctype.lower():
            return False
    # 简单检查响应体大小（避免空文件）
    if resp.headers.get("Content-Length"):
        try:
            if int(resp.headers["Content-Length"]) < 128:  # 128B 作为最低阈值
                return False
        except ValueError:
            pass
    else:
        if len(resp.content) < 128:
            return False
    return True


def try_fetch_image(url: str, timeout: float = 8.0, head_first: bool = True) -> bool:
    """
    尝试获取图片：
    - 优先用 HEAD（轻量），成功后再 GET 确认/保存；
    - 部分站点可能不支持 HEAD，失败时回退 GET。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://img-preview.51jiaoxi.com/",  # 部分站点需要同源或指定 Referer
    }
    session = requests.Session()

    # 先 HEAD
    if head_first:
        try:
            resp = session.head(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code == 405:
                # 不支持 HEAD，改用 GET
                pass
            elif resp.ok:
                # 用 GET 真正获取内容以验证和保存
                resp_get = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
                return is_image_response(resp_get)
        except requests.RequestException:
            # 回退 GET
            pass

    # 直接 GET
    try:
        resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        return is_image_response(resp)
    except requests.RequestException:
        return False


def save_image(url: str, save_dir: str = "downloads", timeout: float = 15.0) -> str:
    """
    下载并保存图片，返回文件路径。目录不存在则创建。
    """
    os.makedirs(save_dir, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://img-preview.51jiaoxi.com/",
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if not is_image_response(resp):
        raise RuntimeError(f"下载失败或非图片响应：{resp.status_code} {resp.headers.get('Content-Type','')}")
    # 根据 URL 推断文件名
    fname = os.path.basename(urlparse(url).path)
    if not fname:
        fname = f"image_{int(time.time())}.bin"
    save_path = os.path.join(save_dir, fname)
    with open(save_path, "wb") as f:
        f.write(resp.content)
    return save_path


def find_first_valid_image_url(
    base_url: str,
    start_ts: int,
    step: int = 1,
    max_tries: int = 10000,
    sleep_sec: float = 0.15,
) -> tuple[str, int] | None:
    """
    从 start_ts 开始，按 step（默认为 +1）递增，最多尝试 max_tries 次。
    找到第一个可以下载图片的 URL 后返回 (url, ts)，否则返回 None。
    """
    consecutive_failures = 0

    for i in range(max_tries):
        ts = start_ts + i * step
        try:
            test_url = replace_timestamp_in_url(base_url, ts)
        except ValueError as e:
            raise e

        ok = try_fetch_image(test_url)
        if ok:
            return test_url, ts

        consecutive_failures += 1

        # 简单退避：连续失败增大睡眠时间，避免触发限流
        if consecutive_failures % 50 == 0:
            time.sleep(min(2.0, sleep_sec * 10))
        else:
            time.sleep(sleep_sec)

    return None


if __name__ == "__main__":
    base = "https://img-preview.51jiaoxi.com/1/3/14914151/0-{ts}/4.jpg?x-oss-process=image/resize,w_794,m_lfit,g_center/format,webp/sharpen,100"
    start = 1697712533700  # 起始时间戳
    result = find_first_valid_image_url(base, start_ts=start, step=1, max_tries=5000, sleep_sec=0.1)

    if result is None:
        print("未在指定范围内找到可下载的图片 URL。")
    else:
        url, ts = result
        print(f"找到可下载图片：ts={ts}\nURL={url}")
        try:
            path = save_image(url, save_dir="downloads")
            print(f"图片已保存到：{path}")
        except Exception as e:
            print(f"保存图片时出错：{e}")