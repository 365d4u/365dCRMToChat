# 阿里云切换候选更新（未上线）

2026-10-21。用户本轮要求准备切换，之前不合 main、不部署的限制仍保留；本轮没有重启、改环境、消费业务队列或写生产数据库。

原项目现已有正式 Git 仓库和 origin/main `871b6d4858860f9dd63a2b80538404bf5bd4932b`。迁移改动从原隔离仓库 `80ec003` 移植为本正式仓库分支 `codex/aliyun-rabbitmq-migration` 的 `f7b25ac`。工作树：`E:/PycharmProjects/365dCRMToChat-aliyun-cutover-20261021`。未推送或合入 main，原独立隔离副本保留为证据。原迁移文档的“原项目没有 Git”是初轮准备时的历史状态。

在此正式仓库候选重新运行 75 项纯合成测试，全部通过。此前三个生产主机的随机 MQ 探针证据仍保留，本轮没有重新进行阿里云联调。

107 服务器只读现场：consumer PID 2195290、tunnel PID 2194959，前后均 active/PID 不变；单 writer、写入开关 true、workspace 1、旧隧道为 `127.0.0.1:35672`。旧持久快照队列 ready/unacked=0、consumer=1；invalid=0。这些只是检查时的快照。

现场 14 个 Python 模块除 media.py 外与原项目一致；media.py 是既有部署差异，本次不覆盖。正式部署仅更新经审阅的 consume.py、rabbitmq.py、cli.py、observer.py。writer、contracts、media、身份映射、回执、env、独立 venv、CPU/内存和服务身份保持。不得启用旧 Respond writer，不允许两个 CRMToChat writer 同时运行。

联动执行稿保存在 CRM 仓库 `docs/operations/aliyun-cutover-20261021.md`。正式授权后先将两个仓库候选分别集成并推送 origin/main，从明确版本构建；先准备阿里云拓扑与持久快照绑定，再阶段 A 自建主端/阿里云 DRAIN，确认所有消费者就绪后才允许阶段 B 阿里云主端/自建 DRAIN。目标 vhost、TLS/实例 ID、权限、消费超时和最大投递次数仍需现场核验。

快照队列继续使用 `.invalid` 死信契约，事务提交后仅 ACK 原来源。回滚优先保留双来源程序、恢复旧端主目标，并继续消费阿里云积压；不能直接回到旧单源版本后停止新端消费。隧道、旧 Broker、队列和业务恢复资料不删除。
