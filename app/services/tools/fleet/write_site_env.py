"""Interactive writer for site.env — the one file an operator edits.

Run through SETUP_SITE.cmd. Asks only what is needed, keeps blank answers as "not set", and
writes the file as UTF-8 with BOM so Notepad shows Chinese correctly.
"""
import pathlib
import sys


def ask(prompt, default="", required=False, secret=False):
    while True:
        label = prompt
        if default:
            label += " [%s]" % default
        if secret:
            label += " (留空=不设置)"
        try:
            value = input(label + ": ").strip()
        except EOFError:
            print("\n没有输入，已取消。")
            sys.exit(1)
        if not value:
            value = default
        if required and not value:
            print("   这一项必填。")
            continue
        return value


def main():
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("site.env")
    if target.exists():
        print("== %s 已存在" % target)
        answer = ask("覆盖它？(y/N)", "N").lower()
        if answer not in ("y", "yes"):
            print("已保留原文件，未修改。")
            return 1

    print("== 现场配置（直接回车用方括号里的默认值）")
    ssid = ask("WiFi 名称", required=True)
    auth = ask("认证方式 1=普通密码(psk) 2=企业802.1X(eap)", "1")
    auth = "eap" if auth.strip() == "2" else "psk"
    identity = ""
    if auth == "eap":
        identity = ask("802.1X 账号（如学号）", required=True)
    password = ask("WiFi 密码", required=True, secret=True)

    print()
    print("== 远程管理（跨网络必须）")
    print("   在你自己组织的 Tailscale 后台生成 auth key：")
    print("   Settings -> Keys -> Generate auth key（勾一次性、24 小时过期）")
    authkey = ask("Tailscale auth key", secret=True)

    print()
    print("== 登录方式")
    print("   你没有私钥，建议设置密码，之后就能 ssh 登录")
    ssh_pass = ask("eora 的登录密码（至少 8 位）", secret=True)
    while ssh_pass and len(ssh_pass) < 8:
        print("   太短了，至少 8 位。")
        ssh_pass = ask("eora 的登录密码", secret=True)

    lines = [
        "# 由 SETUP_SITE.cmd 生成；改完直接重新运行 MK_CARDS.cmd",
        "WIFI_SSID=%s" % ssid,
        "WIFI_AUTH=%s" % auth,
    ]
    if identity:
        lines.append("WIFI_IDENTITY=%s" % identity)
    lines.append("WIFI_PASSWORD=%s" % password)
    lines.append("TAILSCALE_AUTHKEY=%s" % authkey)
    if ssh_pass:
        lines.append("SSH_PASSWORD=%s" % ssh_pass)

    target.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print()
    print("已写入 %s" % target.resolve())
    print("下一步：运行 MK_CARDS.cmd 做卡。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
