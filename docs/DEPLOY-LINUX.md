# Linux 服务器部署指南

适用于 Ubuntu / Debian / CentOS / Rocky 等发行版，含 systemd 守护、
Nginx 反向代理和 HTTPS 配置。

---

## 一、安装 Docker

### Ubuntu / Debian

```bash
# 一键脚本（官方，最省事）
curl -fsSL https://get.docker.com | sh

# 添加当前用户到 docker 组（免 sudo）
sudo usermod -aG docker $USER
newgrp docker
```

### CentOS / Rocky / AlmaLinux

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

### 验证

```bash
docker --version
docker compose version
docker run --rm hello-world
```

---

## 二、部署项目

### 1. 获取代码

```bash
cd /opt
sudo git clone https://github.com/luo-sri/chatgpt2api.git
cd chatgpt2api
```

### 2. 配置

```bash
sudo cp .env.example .env
sudo nano .env
```

```ini
CHATGPT2API_AUTH_KEY=换成一个强密码
TZ=Asia/Shanghai
```

### 3. 启动

```bash
sudo docker compose up -d
sudo docker compose logs --tail 30
```

### 4. 验证

```bash
curl http://127.0.0.1:3100/health
# {"status":"ok"}
```

---

## 三、systemd 守护（可选）

Docker 自带 `restart: unless-stopped` 已经能从崩溃中恢复。
但如果你希望**服务器重启后确保容器起来**（即使 docker 服务启动慢），
可以再加一层 systemd。

创建 `/etc/systemd/system/chatgpt2api.service`：

```ini
[Unit]
Description=ChatGPT2API All-in-One
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/chatgpt2api
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable chatgpt2api
sudo systemctl start chatgpt2api
sudo systemctl status chatgpt2api
```

---

## 四、Nginx 反向代理

面板自带 WebSocket（内置浏览器）和流式响应，反代要特殊配置。

### 安装 Nginx

```bash
sudo apt install -y nginx
# 或
sudo dnf install -y nginx
```

### 配置站点

`/etc/nginx/conf.d/chatgpt2api.conf`：

```nginx
server {
    listen 80;
    server_name ai.example.com;

    # 流式响应必须关掉缓冲
    proxy_buffering off;
    proxy_cache off;

    # 上传大文件（生图参考图）
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:3100;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket（内置浏览器 noVNC 需要）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 长连接超时（对话可能很久）
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

### 生效

```bash
sudo nginx -t
sudo systemctl reload nginx
```

> 注意：内置浏览器（6080）**不建议**一起反代出去，安全风险较大。
> 需要加账号时，用 SSH 隧道更安全：
> `ssh -L 6080:127.0.0.1:6080 user@server`

---

## 五、HTTPS（Let's Encrypt）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ai.example.com
```

按提示操作，certbot 会自动改 Nginx 配置并设置续期定时任务。

验证自动续期：

```bash
sudo certbot renew --dry-run
```

---

## 六、防火墙

只开放必要端口：

```bash
# ufw（Ubuntu）
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# firewalld（CentOS）
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

**不要**对外开放 3100、6080、8888，用反代访问即可。

---

## 七、日志与监控

### 容器日志

```bash
sudo docker compose logs -f
sudo docker compose logs --tail 200
```

### 限制日志大小

`docker-compose.yml` 里加：

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

否则日志会无限增长占满磁盘。

### 磁盘检查

```bash
df -h
docker system df
```

定期清理无用镜像：

```bash
docker image prune -f
```

---

## 八、性能调优

### shm 大小

Chromium 需要较大的共享内存，否则会崩：

```yaml
shm_size: 512mb
```

### 内存限制

```yaml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '2'
```

### 时区

必须设 `TZ=Asia/Shanghai`，否则日志时间和额度重置时间会差 8 小时。

---

## 九、更新维护

```bash
cd /opt/chatgpt2api
sudo git pull
sudo docker compose up -d --build
```

`data/` 会保留，账号和配置不丢。

### 备份

```bash
# 每天凌晨 3 点备份
cat > /etc/cron.d/chatgpt2api-backup << 'EOF'
0 3 * * * root cd /opt/chatgpt2api && tar -czf /backup/c2a-$(date +\%F).tar.gz data/ && find /backup -name 'c2a-*.tar.gz' -mtime +7 -delete
EOF
```

---

## 十、常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 502 Bad Gateway | 容器没起来 | `docker compose ps` 看状态 |
| 流式输出变成一次性返回 | Nginx 缓冲没关 | 加 `proxy_buffering off` |
| 内置浏览器连不上 | WebSocket 头没配 | 加 `Upgrade` / `Connection` 头 |
| 对话中途断开 | 超时太短 | `proxy_read_timeout 300s` |
| 账号数据丢失 | data 没挂载 | 检查 volumes 路径 |
| 磁盘满 | 日志/镜像堆积 | 加日志限制，`docker system prune` |

---

## 十一、安全建议

1. **必须改掉默认密钥**：`.env` 里 `CHATGPT2API_AUTH_KEY`
2. **不要裸奔 3100**：用 Nginx + HTTPS，或至少限制 IP
3. **6080 只走 SSH 隧道**：不要对公网开放
4. **定期更新**：`git pull` + 重建镜像
5. **备份 data/**：账号 token 都在里面，丢了要重新登录所有号
6. **用普通用户跑**：不要把容器设为 privileged

---

## 下一步

- [Docker 通用指南](DEPLOY-DOCKER.md)
- [NAS 部署](DEPLOY-NAS.md)
- [API 文档](API.md)
- [常见问题](FAQ.md)
