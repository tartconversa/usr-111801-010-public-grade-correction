# 景区资料协作台账：公开等级目录的更正传播

服务登记资料来源、字段、原件、使用许可、数据产品与交付凭据，并围绕主管部门
公告的发布、更正与撤回维护一条只追加的版本链。示例主体和记录均为虚构，不
连接真实文旅部门。

需要 Python 3.10 或更新版本，不依赖第三方包。

运行项目测试：python -m unittest discover -s tests -v。
检查源码：python -m compileall -q exchange。
运行本地演练：python -m exchange --database demo.db。

## 模块职责

- `catalog.py` 登记来源字段和原件；目录条目可携带 `scenic_area` 与公告依据。
- `grants.py` 与 `policy.py` 管理使用边界。
- `announcements.py` 维护公告版本链、更正关系、当前效力与待重新确认查询。
- `products.py` 编排资料，`delivery.py` 出具回执并执行公告效力闸门，`audit.py` 记录操作。

## 更正如何传播

公告的每次发布（publish）、更正（correction）、撤回（withdrawal）都向
`announcements` 追加一行，版本之间的依据关系保存在 `announcement_relations`
（`corrects` / `withdraws`）。任何旧公告、旧目录条目和旧回执都不会被修改或删除。

- **旧版本说明当时依据**：交付回执的 `basis_snapshot` 固化每个输入条目当时
  依据的公告编号与摘要；`explain_delivery` 逐项给出 `current` / `stale` 状态
  和受影响景区，旧条目永久可查。
- **新领取只获得当前可核实版本**：交付时校验每个输入条目的公告依据是否仍在
  有效集合内，过期依据以 `stale-announcement` 拒绝，需要用当前条目重新编排。
- **撤回不靠倒放消息**：撤回只追加一条 `withdraws` 记录。当前效力由整条链
  折叠推导——被未撤回更正取代的版本失效，被撤回更正所取代的旧版本自动恢复
  效力，没有任何回写或删除动作。
- **待重新确认可按景区和领取方查明**：`pending_reconfirmations(scenic_area=…,
  recipient=…)` 完全派生自历史回执与当前公告链；同一领取方之后领取过包含该
  景区当前条目的新回执后，待办自动消除。
