# 协作开发约定

本仓库是三人共享的 Rescue-Dog 工程。`main` 只接收通过 GitHub Pull Request
且 CI 通过的改动；真实机械狗 SDK、标定数据和比赛原始资料暂不直接提交。

## 开始一次改动

```bash
git clone https://github.com/JayooYuan/Rescue-Dog.git
cd Rescue-Dog/interfaces_v0.2.1
python -m unittest discover -s tests -v
```

从 `main` 创建短分支，建议使用 `codex/<topic>` 或 `<member>/<topic>`。一个
Pull Request 聚焦一个模块，描述测试命令、已知限制和是否需要实机标定。

## 接口纪律

- `rescue_contracts/types.py` 与 `rescue_contracts/interfaces.py` 是公共契约，
  不要在个人分支静默修改；需要变更时先在 PR 中说明版本影响。
- 所有请求使用新的非空 `request_id`；重复 ID 只能得到幂等结果，不能延长 TTL
  或重复机械臂动作。
- `CommandAck.accepted=True` 不代表实物已经运动或抓取成功。
- 机械臂完成状态默认是 `DONE_UNVERIFIED`；没有可信传感器证据不得改报
  `SUCCESS`。
- 运动命令必须经过 `SAFE/AUTO/REMOTE` 控制权和底盘/机械臂互锁检查。
- 不要提交密码、设备 IP、遥控频段、摄像头采集物或生成日志；这些内容由
  `.gitignore` 排除并通过安全渠道共享。

## 提交前检查

在 `interfaces_v0.2.1` 目录运行：

```bash
python -m unittest discover -s tests -v
python -m examples.demo_mock
python -m examples.demo_fsm
```

CI 会在 Python 3.10–3.13 上重复协议和 FSM 测试。合并前请把待实机确认的
SDK 能力、坐标标定和安全停车能力写入 PR，而不是用 Mock 结果替代实测结论。
