"""Configure and check the fixed local PPT credential without echoing it."""
import argparse
import getpass
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile

import requests

API = "https://xiaomiao-ai.com/api/ppt/v1"
CONFIG = Path(__file__).resolve().parents[1] / "config"
KEYCHAIN_SERVICE = "com.cell-skills.cell-ppt"
KEY_FORMAT = re.compile(r"[A-Za-z0-9_.-]{24,180}")


def credential_path():
    if sys.platform == "win32":
        return CONFIG / "ppt-api-key.dpapi"
    if sys.platform == "darwin":
        return CONFIG / "ppt-api-key.keychain"
    raise ValueError("PPT API 配置支持 Windows 和 macOS")


def windows_dpapi():
    try:
        import win32crypt
    except ImportError:
        raise ValueError("PPT 密钥加密需要 Windows Python 的 pywin32") from None
    return win32crypt


def mac_keychain(*args, input_text=None):
    return subprocess.run(["/usr/bin/security", *args], input=input_text,
                          capture_output=True, text=True, timeout=90)


def load():
    path = credential_path()
    if not path.is_file():
        raise ValueError("请先配置 PPT 客户端 API 密钥")
    try:
        saved = path.read_text(encoding="ascii").strip()
        if sys.platform == "win32":
            dpapi = windows_dpapi()
            key = dpapi.CryptUnprotectData(bytes.fromhex(saved), None, None, None, 0)[1].decode("utf-16-le")
        else:
            if saved != KEYCHAIN_SERVICE:
                raise ValueError("Invalid Keychain locator")
            result = mac_keychain("find-generic-password", "-s", KEYCHAIN_SERVICE,
                                  "-a", getpass.getuser(), "-w")
            key = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        raise ValueError("无法读取已配置的 PPT 密钥，请重新配置") from None
    if not KEY_FORMAT.fullmatch(key):
        raise ValueError("无法读取已配置的 PPT 密钥，请重新配置")
    return key


def verify(key):
    if not KEY_FORMAT.fullmatch(key):
        raise ValueError("PPT 客户端 API 密钥格式无效")
    with requests.Session() as session:
        response = session.get(API + "/balance", headers={"Authorization": f"Bearer {key}"},
                               allow_redirects=False, timeout=(8, 15))
    if response.status_code in {401, 403}:
        raise ValueError("PPT 客户端 API 密钥无法通过验证，请重新配置")
    if response.status_code != 200:
        raise ValueError(f"暂时无法验证 PPT API（HTTP {response.status_code}）")
    payload = response.json()
    pages = payload.get("available_pages") if isinstance(payload, dict) else None
    if type(pages) is not int or pages < 0:
        raise ValueError("PPT API 返回的余额无效")
    return pages


def configure(key):
    path = credential_path()
    balance = verify(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        dpapi = windows_dpapi()
        data = key.encode("utf-16-le")
        blob = dpapi.CryptProtectData(data, "cell_ppt API", None, None, None, 0)
        if dpapi.CryptUnprotectData(blob, None, None, None, 0)[1] != data:
            raise ValueError("PPT 密钥加密校验失败")
        saved = blob.hex()
    else:
        # security's interactive mode takes the command on stdin. The secret never becomes a process argument.
        account = getpass.getuser()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", account):
            raise ValueError("无法确定 macOS 钥匙串账户")
        command = f'add-generic-password -U -s {KEYCHAIN_SERVICE} -a {account} -w {key}\n'
        mac_keychain("-i", input_text=command)
        result = mac_keychain("find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w")
        if result.returncode != 0 or result.stdout.strip() != key:
            raise ValueError("无法保存或读取 macOS 钥匙串中的 PPT 密钥")
        saved = KEYCHAIN_SERVICE
    with NamedTemporaryFile(dir=path.parent, mode="w", encoding="ascii", delete=False) as temporary:
        staged = Path(temporary.name)
        temporary.write(saved)
    try:
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)
    return balance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("check")
    actions.add_parser("setup").add_argument("--from-stdin", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "setup":
            if not args.from_stdin and not sys.stdin.isatty():
                raise ValueError("请在本机交互终端输入，或用 --from-stdin 安全传入 PPT 密钥")
            key = sys.stdin.readline() if args.from_stdin else getpass.getpass("PPT API Key: ")
            pages = configure(key.strip())
        else:
            pages = verify(load())
        print(json.dumps({"configured": True, "available_pages": pages}, ensure_ascii=False))
        return 0
    except ValueError as error:
        message = str(error)
    except (OSError, requests.RequestException, subprocess.SubprocessError):
        message = "暂时无法完成 PPT API 检查，请检查网络或本机凭据存储"
    print(json.dumps({"configured": False, "error": message}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
