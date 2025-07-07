# 在服务器root菜单下新建一个文件夹存放脚本文件，然后把这6个文件导入进去，在该文件夹下另外新建一个命名为session的文件夹，用来存放不同手机号的session文件

## 📦 环境准备

建议使用 Ubuntu 服务器

1✅、安装python3
```bash
sudo apt update
sudo apt install python3 python3-pip -y
```

2✅、安装依赖库
```bash
pip install fastapi uvicorn pydantic telethon python-dotenv redis httpx "aiogram>=3.0.0,<4.0.0"
```

3✅、开启pm2脚本自动运行（开启后关闭服务器依然运行）
```bash
sudo npm install -g pm2
pm2 start bot.py --name telegram-bot
pm2 start main.py --name telegram-api
pm2 start login.py --name telegram-login-api
pm2 save
pm2 startup
```

4✅、脚本重启（如果修改了代码）
```bash
pm2 restart telegram-bot
pm2 restart telegram-api
pm2 restart telegram-login-api
```

5✅、查看脚本日志
```bash
pm2 logs telegram-bot
pm2 logs telegram-api
pm2 logs telegram-login-api
```
