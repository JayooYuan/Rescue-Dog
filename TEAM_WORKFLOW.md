# Rescue-Dog 团队协作操作指南

本文是三人协作的日常操作手册。仓库的稳定分支是 `main`；个人开发必须在短功能分支进行，并通过 Pull Request 合并。

## 1. 一次性仓库配置

管理员在 GitHub 仓库中完成：

1. `Settings -> Collaborators` 添加 A、B、C 三位队员。
2. `Settings -> Rulesets -> New branch ruleset` 新建 `protect-main`，目标分支填 `main`。
3. 启用：必须通过 Pull Request、至少 1 人审核、禁止强制推送、禁止删除分支。
4. CI 修复后，把成功的 `contract-tests` 检查加入必需状态检查。

规则设置完成后，任何人都不能直接把未经审核的提交推入 `main`。

## 2. 三人分工与代码边界

| 角色 | 分支示例 | 负责内容 | 交接给 B 的接口 |
| --- | --- | --- | --- |
| A 视觉 | `a/vision` | 黑线、黄/黑立牌、红绿蓝球、ROI/HSV 和离线测试 | `VisionResult` |
| B 运动与主控 | `b/motion-fsm` | MotionAPI、控制权、TTL、互锁、FSM、蜂鸣器协调和集成 | `MotionAck`、FSM 事件 |
| C 机械臂 | `c/arm` | 异步动作、`action_id` 幂等、超时、取消和动作模板 | `ActionAck`、`ActionResult` |

三人共同遵守：

- 不要在个人分支静默修改 `interfaces_v0.2.1/rescue_contracts/types.py` 或 `interfaces.py`。
- B 不读取 A 的 HSV 中间变量，也不直接控制 C 的舵机角度。
- 未经传感器验证的机械臂完成状态保持 `DONE_UNVERIFIED`。
- 未标定的距离返回 `None`；Mock 结果不能代替实机安全验证。

## 3. 从 Issue 到合并的标准流程

### 3.1 领取任务

先在 GitHub Issue 中写清楚目标、验收标准和负责人。建议标题格式：

```text
[A] VisionResult and black-line detection
[B] Motion TTL and rescue FSM
[C] Arm action lifecycle and idempotency
[Integration] First acceptance run
```

一个 Issue 尽量对应一个 Pull Request，不把视觉、运动和机械臂混在同一个功能 PR 中。

### 3.2 创建分支

```powershell
git clone https://github.com/JayooYuan/Rescue-Dog.git
cd Rescue-Dog
git switch main
git pull --ff-only origin main
git switch -c a/vision
```

B、C 把最后一行替换为 `b/motion-fsm`、`c/arm`。分支创建后只由本人维护，其他人通过 PR 审核，不直接推送到该分支。

### 3.3 本地验证和提交

在 `interfaces_v0.2.1` 目录执行：

```powershell
python -m unittest discover -s tests -v
python -m examples.demo_mock
python -m examples.demo_fsm
```

确认通过后回到仓库根目录：

```powershell
git status
git diff --check
git add <实际修改的文件>
git commit -m "feat(vision): add line and sign detection"
git push -u origin a/vision
```

不要使用 `git add .` 把密码、视频、日志或本地标定文件一并提交。

### 3.4 创建和审核 Pull Request

PR 的目标分支固定为 `main`，描述必须包含：

- 改了什么、涉及哪个模块；
- 本地运行过的测试命令；
- 已知限制和是否需要实机标定；
- 是否修改公共契约；
- 是否提交了真实设备资料（应为“否”）。

审核人重点检查模块边界、异常路径、幂等、TTL、模式互锁和安全状态。CI 失败时先看失败步骤日志，不要用“本地通过”替代 CI 结果。

### 3.5 合并后的同步

PR 合并后，所有成员都同步自己的本地 `main`：

```powershell
git switch main
git pull --ff-only origin main
git switch a/vision
git rebase main
git push --force-with-lease
```

`--force-with-lease` 只能用于本人独占的功能分支，不能用于 `main` 或队友正在使用的分支。

## 4. 第一轮联调验收

合并 A、C 后，由 B 从最新 `main` 开集成 PR，完成：

1. 黑牌识别 -> 停止 -> 报警 -> 击倒请求 -> 继续循迹；
2. 抓球 -> 投杯 -> 返航；
3. 过期帧、无目标、运动 TTL、动作超时、互锁和 SAFE 状态恢复；
4. 记录仍需实机确认的 SDK、标定和急停能力。

验收证据优先使用测试输出、PR 检查和脱敏记录；不要把原始视频、设备密码或完整运行日志上传到仓库。

## 5. 常见问题

- **CI 报 `Start directory is not importable: 'tests'`**：检查工作流是否在 `interfaces_v0.2.1` 目录运行。
- **分支落后于 main**：先 `git fetch origin`，再在自己的分支执行 `git rebase origin/main`。
- **公共接口需要变化**：先开 Issue，三人统一字段和版本，再由一个 PR 同时修改类型、协议和测试。
- **发生冲突**：只解决自己的功能分支冲突；不要用强制重置覆盖队友工作。
