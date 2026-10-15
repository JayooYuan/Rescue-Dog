# 四足机械狗 · 接口协议与 Mock 开工包 v0.2.1

**这是一套可发给 A/B/C 三名开发成员直接开工的公共协议，不是已连接真实机械狗的 SDK。**

## 开始使用

请安装 Python **3.10 或更高版本**，进入本目录运行：

```bash
python -m unittest discover -s tests -v
```

当前提供协议基础测试以及 B 组 FSM/模式看门狗测试，检查类型/时序/权限/互锁/幂等
和常见异常。无需联网或连接真实机器人。

运行一个模拟“黑牌→停车→机械臂击倒请求”的示例：

```bash
python -m examples.demo_mock
python -m examples.demo_fsm
```

## 重要文件

- `接口协议_v0.2.1.md`：**正式分发给三名队员的规范**。请先阅读。
- `rescue_contracts/types.py`：所有公共枚举和数据结构；各成员必须直接导入，不许复制一份自己改。
- `rescue_contracts/interfaces.py`：Vision、Motion、Arm 的 Python Protocol 签名。
- `mocks/fake_devices.py`：不依赖硬件的示例 Mock（包括可控时钟、模式、互锁、TTL 和异步动作）。
- `tests/test_contracts.py`：最小协议契约测试。
- `三人任务单_v0.2.1.md`：每个人的开工任务与交付范围。
- `fsm.py`：只依赖公共协议的自主任务 FSM Mock（循迹、识牌、报警、绕行/击倒、找球、投杯、返航）。
- `FSMConfig`：集中管理报警距离、控制 TTL、动作超时和归一化运动参数，避免现场参数散落在状态逻辑中。

## 开工纪律

1. 暂不修改 `rescue_contracts/`。确有需求时三人一起讨论，再统一更新版本。
2. A 负责视觉识别；B 负责运动、主控状态机、控制权和蜂鸣器协调；C 负责机械臂动作框架。
3. `CommandAck.accepted=True` 不代表真实动作已经完成，抓取更不能凭动作序列完成就报 SUCCESS。
4. Mock 里的故障恢复只是软件模拟；没有实物之前不能宣称已经验证下位机安全停车或机械臂取消。

## 兼容性

已知的 XGO 教程属于参考，**并不代表**比赛最终实物一定运行对应 SDK/固件。初期只写通用协议/Mock/视觉离线算法，等待设备到手后在独立适配器中接入真实硬件。
