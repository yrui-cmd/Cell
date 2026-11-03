# 内置第三方 Skill 来源

以下文件按固定提交原样保存，运行时不访问 GitHub：

| 名称 | 上游仓库 | 固定提交 | 内置文件 SHA-256 | 许可证 |
| --- | --- | --- | --- | --- |
| lieflat-less-ai-tone | https://github.com/larashero3-dotcom/lieflat-less-ai-tone | `27d29232f10124db904ca9c0536d0b67cb3b2833` | `1DB087D4DB618CF635EC15B304803F3A219D57F92297E1103F922F2F051C8A35` | MIT，见对应目录 `LICENSE` |
| anti-defensive-writing | https://github.com/Kiterlin/anti-defensive-writing | `f516147d017a3fe43ae99192cb89d8261b0c8679` | `15090C331815FD869826552A9A65F1B4D8C2C45A60C0AC0ADD22165C450E3174` | MIT，见对应目录 `LICENSE` |

主 Skill 通过 `references/human-writing-pass.md` 限定启用位置、适用语言和科研写作边界。上游示例不提供综述事实，且不能覆盖证据与方法要求。

2026-10-31本地兼容修复：上表SHA-256表示引入时的原始SKILL.md，不是修改后文件的摘要。内部入口改名为RULES.md，引用研究说明改为同一上游commit的真实URL；许可证保留。当前文件字节由发布包SHA256SUMS.txt核验。
