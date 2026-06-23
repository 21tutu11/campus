from flask import Flask, request, jsonify, session, send_from_directory, redirect, Response, stream_with_context
from flask_cors import CORS
import hashlib
import json
from web3 import Web3
from db import get_conn
# 新增本地命令行调用依赖
import subprocess
import requests
import os

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app, supports_credentials=True)
app.secret_key = "campus_rental_2026_secret_key"

# ===================== Web3 全局配置 =====================
GANACHE_RPC = "http://127.0.0.1:7545"
w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))
if not w3.is_connected():
    print("警告：Ganache未启动，请先打开Ganache客户端！")

# 读取Truffle部署生成的合约文件
with open("../build/contracts/CampusRental.json", "r", encoding="utf-8") as f:
    contract_info = json.load(f)
CONTRACT_ADDR = contract_info["networks"]["1337"]["address"]
CONTRACT_ABI = contract_info["abi"]
rental_contract = w3.eth.contract(address=CONTRACT_ADDR, abi=CONTRACT_ABI)

# Ganache钱包私钥映射
ganache_wallet_key_map = {
    "0x383ce9e3C66E87C05046E42b579E1A950da4A000": "0x4d6b5e7b30062431a8a72c66ec9fead3488f9d408be3dc82f90b7c8e5b424fa5",
    "0xBd7615f43906Eb9740c4dB108BC151015A3DfcB1": "0xcacba46f0ce7497dc252ef3b5b187360db0d1a31686322477793856e9d5eb3d4",
    "0x5D1fa282639B95d445a3b30cb6434d674C9dc01A": "0xdea52fe4e06062eb311665f3931b9eeca2f4c15deb701dcc1667a962a6951e0d",
}

def get_private_key_by_addr(wallet_addr):
    lower_addr = wallet_addr.lower()
    for addr, pk in ganache_wallet_key_map.items():
        if addr.lower() == lower_addr:
            return pk
    return None

def encrypt_password(raw_str):
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

# =====================【本地命令行ipfs add上传接口】 =====================
@app.route("/api/upload_ipfs_img", methods=["POST"])
def upload_ipfs_img():
    if "itemImg" not in request.files:
        return jsonify({"code": -1, "msg": "请选择图片文件"})
    file = request.files["itemImg"]
    allow_mime = ["image/jpeg", "image/jpg", "image/png", "image/gif"]
    if file.mimetype not in allow_mime:
        return jsonify({"code": -1, "msg": "仅支持 jpg/png/gif 格式图片"})
    file_data = file.read()
    if len(file_data) > 5 * 1024 * 1024:
        return jsonify({"code": -1, "msg": "图片大小不能超过5MB"})
    file.seek(0)
    temp_path = "temp_upload_img.tmp"
    file.save(temp_path)
    try:
        cmd_out = subprocess.check_output(["ipfs", "add", temp_path], encoding="utf-8")
        # 拆分第一行，第二个元素才是Qm开头真实CID
        first_line = cmd_out.strip().splitlines()[0]
        parts = first_line.split()
        real_cid = parts[1]
        # 锁定文件
        subprocess.run(["ipfs", "pin", "add", real_cid])
        os.remove(temp_path)
        # 后端统一返回代理地址，前端无需拼接8080直链
        img_preview_url = f"/ipfs_proxy?cid={real_cid}"
        return jsonify({
            "code": 0,
            "msg": "图片上传IPFS成功",
            "cid": real_cid,
            "imgUrl": img_preview_url
        })
    except Exception as err:
        return jsonify({
            "code": -1,
            "msg": "上传失败，请确认ipfs daemon终端保持开启",
            "error": str(err)
        })

# ===================== IPFS流式代理接口 =====================
@app.route("/ipfs_proxy")
def ipfs_proxy():
    cid = request.args.get("cid", "")
    if not cid or cid.startswith("temp_"):
        return "无效图片CID", 400
    try:
        # 端口改为8081，匹配当前ipfs daemon网关
        upstream = requests.get(f"http://127.0.0.1:8081/ipfs/{cid}", stream=True, timeout=10)
        upstream.raise_for_status()
        return Response(
            stream_with_context(upstream.iter_content(chunk_size=1024)),
            mimetype=upstream.headers.get("Content-Type", "image/jpeg")
        )
    except requests.exceptions.ConnectionError:
        return "IPFS网关端口错误，当前网关8081", 503
    except Exception as e:
        return f"图片读取失败：{str(e)}", 503

# ===================== 页面路由 =====================
@app.route("/")
def root_redirect():
    return redirect("/login.html")

@app.route("/index")
def index_page():
    if "uid" not in session:
        return redirect("/login.html?err=请先登录账号")
    return send_from_directory("../frontend", "index.html")

@app.route("/publishing")
def publishing():
    if "uid" not in session:
        return redirect("/login.html?err=请登录后访问页面")
    return send_from_directory("../frontend", "publish.html")

@app.route("/order.html")
def order_page():
    if "uid" not in session:
        return redirect("/login.html?err=请登录后访问页面")
    return send_from_directory("../frontend", "order.html")

# ===================== 用户登录注册 =====================
@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("name")
    password = request.form.get("pwd")
    if not username or not password:
        return redirect("/login.html?err=用户名和密码不能为空")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, pwd FROM user WHERE name=%s", (username,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    if not user_data or user_data[1] != encrypt_password(password):
        return redirect("/login.html?err=账号或密码错误")
    session["uid"] = user_data[0]
    return redirect("/index")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("name")
    password = data.get("pwd")
    email = data.get("mail", "")
    if not username or not password:
        return jsonify({"code": -1, "msg": "用户名、密码不能为空"})
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM user WHERE name=%s", (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"code": -1, "msg": "该用户名已被注册"})
    cur.execute("INSERT INTO user(name, pwd, mail, addr) VALUES(%s, %s, %s, '')",
                (username, encrypt_password(password), email))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"code": 0, "msg": "注册成功，请前往登录", "url": "/login.html"})

# ===================== 钱包绑定 =====================
@app.route("/bind_wallet", methods=["POST"])
def bind_wallet():
    if "uid" not in session:
        return jsonify({"code": -1, "msg": "请先登录"})
    login_uid = session["uid"]
    wallet_addr = request.form.get("wallet_addr").strip()
    if not wallet_addr:
        return jsonify({"code": -1, "msg": "钱包地址不能为空"})
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM user WHERE addr = %s AND id != %s", (wallet_addr, login_uid))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"code": -1, "msg": "该钱包已绑定其他账号，无法重复绑定"})
    cur.execute("UPDATE user SET addr=%s WHERE id=%s", (wallet_addr, login_uid))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"code": 0, "msg": "钱包绑定成功"})

@app.route("/check_wallet_used", methods=["POST"])
def check_wallet_used():
    wallet_addr = request.form.get("wallet_addr").strip()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM user WHERE addr = %s", (wallet_addr,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"used": bool(res)})

@app.route("/get_bind_wallet", methods=["GET"])
def get_bind_wallet():
    if "uid" not in session:
        return jsonify({"code": -1, "msg": "未登录"})
    user_id = session["uid"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT addr FROM user WHERE id=%s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    bind_addr = res[0] if res else ""
    return jsonify({"code": 0, "wallet_addr": bind_addr})

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login.html?tip=已退出登录")

# ===================== 发布商品 =====================
@app.route("/publish_item", methods=["POST"])
def publish_item():
    try:
        if "uid" not in session:
            return jsonify({"code": -1, "msg": "请先登录账号"})
        user_id = session["uid"]
        title = request.form.get("title")
        item_desc = request.form.get("item_desc", request.form.get("desc", "无商品描述"))
        daily_rent = int(request.form.get("daily_rent"))
        deposit = int(request.form.get("deposit"))
        img_cid = request.form.get("img_cid", "")

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT addr FROM user WHERE id=%s", (user_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        if not res or res[0] is None:
            return jsonify({"code": -1, "msg": "请先绑定MetaMask钱包"})
        checksum_addr = w3.to_checksum_address(res[0])
        user_private_key = ganache_wallet_key_map.get(checksum_addr)
        if not user_private_key:
            return jsonify({"code": -1, "msg": "当前钱包无匹配私钥，无法上链"})

        tx = rental_contract.functions.publishItem(daily_rent, deposit).build_transaction({
            "from": checksum_addr,
            "nonce": w3.eth.get_transaction_count(checksum_addr),
            "gas": 3000000,
            "gasPrice": w3.to_wei(20, "gwei")
        })
        signed_tx = w3.eth.account.sign_transaction(tx, user_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        total_item = rental_contract.functions.getItemCount().call()
        chain_item_id = total_item - 1

        db_conn = get_conn()
        db_cur = db_conn.cursor()
        insert_sql = "INSERT INTO item(uid, title, item_desc, price, deposit, on_shelf, chain_id, img_cid) VALUES(%s, %s, %s, %s, %s, 1, %s, %s)"
        db_cur.execute(insert_sql, (user_id, title, item_desc, daily_rent, deposit, chain_item_id, img_cid))
        db_conn.commit()
        db_cur.close()
        db_conn.close()

        return jsonify({"code": 0, "msg": "商品发布成功", "item_id": chain_item_id, "tx_hash": tx_hash.hex()})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code": -999, "msg": f"服务器异常：{str(e)}"})

# 商品上下架
@app.route("/off_shelf", methods=["POST"])
def off_shelf_item():
    try:
        if "uid" not in session:
            return jsonify({"code": -1, "msg": "请登录"})
        user_id = session["uid"]
        chain_item_id = int(request.form.get("item_id"))
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT uid FROM item WHERE chain_id=%s", (chain_item_id,))
        item_owner = cur.fetchone()
        cur.close()
        conn.close()
        if not item_owner or item_owner[0] != user_id:
            return jsonify({"code": -1, "msg": "仅发布者可操作"})
        db_conn = get_conn()
        db_cur = db_conn.cursor()
        db_cur.execute("UPDATE item SET on_shelf=0 WHERE chain_id=%s", (chain_item_id,))
        db_conn.commit()
        db_cur.close()
        db_conn.close()
        return jsonify({"code": 0, "msg": "商品下架成功"})
    except Exception as e:
        return jsonify({"code": -999, "msg": f"下架失败：{str(e)}"})

@app.route("/on_shelf", methods=["POST"])
def on_shelf_item():
    try:
        if "uid" not in session:
            return jsonify({"code": -1, "msg": "请登录"})
        user_id = session["uid"]
        chain_item_id = int(request.form.get("item_id"))
        conn = get_conn()
        cur = conn.cursor()
        # 1. 校验是否为商品发布者
        cur.execute("SELECT id, uid FROM item WHERE chain_id=%s", (chain_item_id,))
        item_info = cur.fetchone()
        if not item_info or item_info[1] != user_id:
            cur.close()
            conn.close()
            return jsonify({"code": -1, "msg": "仅发布者可操作"})
        item_db_id = item_info[0]
        # 2. 查询是否存在未归还的租赁订单
        cur.execute("SELECT id FROM rent WHERE iid=%s AND status=0", (item_db_id,))
        rent_running = cur.fetchone()
        cur.close()
        conn.close()
        # 存在进行中订单，禁止上架
        if rent_running:
            return jsonify({"code": -1, "msg": "该商品当前已出租，需买家归还完成后才能重新上架"})
        
        # 无租赁占用，执行上架
        db_conn = get_conn()
        db_cur = db_conn.cursor()
        db_cur.execute("UPDATE item SET on_shelf=1 WHERE chain_id=%s", (chain_item_id,))
        db_conn.commit()
        db_cur.close()
        db_conn.close()
        return jsonify({"code": 0, "msg": "商品重新上架成功"})
    except Exception as e:
        return jsonify({"code": -999, "msg": f"上架失败：{str(e)}"})

# 修改商品
@app.route("/edit_item", methods=["POST"])
def edit_item():
    try:
        if "uid" not in session:
            return jsonify({"code": -1, "msg": "请先登录"})
        user_id = session["uid"]
        chain_item_id = int(request.form.get("item_id"))
        new_title = request.form.get("title")
        new_desc = request.form.get("desc")
        new_daily = int(request.form.get("daily_rent"))
        new_deposit = int(request.form.get("deposit"))
        new_img_cid = request.form.get("img_cid", "")
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT uid, addr FROM item LEFT JOIN user ON item.uid=user.id WHERE chain_id=%s", (chain_item_id,))
        item_info = cur.fetchone()
        cur.close()
        conn.close()
        if not item_info or item_info[0] != user_id:
            return jsonify({"code": -1, "msg": "仅发布者可修改"})
        owner_wallet = item_info[1]
        if not owner_wallet:
            return jsonify({"code": -1, "msg": "发布者未绑定钱包"})
        checksum_addr = w3.to_checksum_address(owner_wallet)
        pk = ganache_wallet_key_map.get(checksum_addr)
        if not pk:
            return jsonify({"code": -1, "msg": "私钥不存在，无法上链修改"})
        tx = rental_contract.functions.updateItemPrice(chain_item_id, new_daily, new_deposit).build_transaction({
            "from": checksum_addr,
            "nonce": w3.eth.get_transaction_count(checksum_addr),
            "gas": 3000000,
            "gasPrice": w3.to_wei(20, "gwei")
        })
        signed_tx = w3.eth.account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        db_conn = get_conn()
        db_cur = db_conn.cursor()
        db_cur.execute("UPDATE item SET title=%s, item_desc=%s, price=%s, deposit=%s, img_cid=%s WHERE chain_id=%s",
                       (new_title, new_desc, new_daily, new_deposit, new_img_cid, chain_item_id))
        db_conn.commit()
        db_cur.close()
        db_conn.close()
        return jsonify({"code": 0, "msg": "商品修改成功", "tx_hash": tx_hash.hex()})
    except Exception as e:
        return jsonify({"code": -999, "msg": f"修改失败：{str(e)}"})

# ===================== 租赁接口 =====================
@app.route("/create_rent", methods=["POST"])
def create_rent():
    db_conn = None
    try:
        if "uid" not in session:
            return jsonify({"code": -1, "msg": "请登录后操作"})
        user_id = session["uid"]

        # 捕获数字转换异常，重命名变量为rent_day，和数据表字段统一
        try:
            chain_item_id = int(request.form.get("item_id"))
            rent_day = int(request.form.get("rent_days"))
        except ValueError:
            return jsonify({"code": -1, "msg": "租赁天数/商品ID必须为有效数字"})

        receiver_name = request.form.get("receiver_name", "").strip()
        receiver_phone = request.form.get("receiver_phone", "").strip()
        receiver_addr = request.form.get("receiver_addr", "").strip()

        # 租赁天数校验
        if rent_day < 1:
            return jsonify({"code": -1, "msg": "租赁天数必须大于0"})
        if not receiver_name or not receiver_phone or not receiver_addr:
            return jsonify({"code": -1, "msg": "收件人、手机号、收货地址不能为空"})

        # 查询商品基础信息
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, uid, on_shelf, price, deposit FROM item WHERE chain_id=%s", (chain_item_id,))
        item_info = cur.fetchone()
        cur.close()
        conn.close()
        if not item_info:
            return jsonify({"code": -1, "msg": "商品不存在"})
        item_db_id, item_publish_uid, item_shelf_status, daily_rent, deposit = item_info

        # 业务约束：不能租赁自己发布的商品
        if user_id == item_publish_uid:
            return jsonify({"code": -1, "msg": "无法租赁自己发布的商品"})
        # 业务约束：商品已下架/已出租
        if item_shelf_status == 0:
            return jsonify({"code": -1, "msg": "商品已下架/已租出"})

        # 读取链上商品数据
        item_chain_data = rental_contract.functions.itemList(chain_item_id).call()
        deposit_value = item_chain_data[2]
        chain_available = item_chain_data[3]
        if not chain_available:
            return jsonify({"code": -1, "msg": "链上商品已被租赁"})

        total_rent = daily_rent * rent_day
        total_pay_show = total_rent + deposit

        # 开启数据库事务
        db_conn = get_conn()
        db_conn.autocommit = False
        db_cur = db_conn.cursor()
        # 更新商品为已下架状态
        db_cur.execute("UPDATE item SET on_shelf=0 WHERE chain_id=%s", (chain_item_id,))

        # 获取用户钱包地址
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT addr FROM user WHERE id=%s", (user_id,))
        user_wallet_res = cur.fetchone()
        cur.close()
        conn.close()
        if not user_wallet_res or not user_wallet_res[0]:
            db_conn.rollback()
            return jsonify({"code": -1, "msg": "请绑定钱包"})
        user_wallet = user_wallet_res[0]
        user_pk = get_private_key_by_addr(user_wallet)
        if not user_pk:
            db_conn.rollback()
            return jsonify({"code": -1, "msg": "钱包无匹配私钥"})

        # 构造并发送链上租赁交易
        tx = rental_contract.functions.createRentOrder(chain_item_id, rent_day).build_transaction({
            "from": user_wallet,
            "value": deposit_value,
            "nonce": w3.eth.get_transaction_count(user_wallet),
            "gas": 3000000,
            "gasPrice": w3.to_wei(20, "gwei")
        })
        signed_tx = w3.eth.account.sign_transaction(tx, user_pk)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)

        # 获取链上订单ID
        chain_order_id = rental_contract.functions.getOrderCount().call() - 1

        # 插入租赁订单，参数与SQL字段严格一一对应，rent_day正常存入
        db_cur.execute("""
        INSERT INTO rent(
            iid, rent_uid, own_uid, rent_day, daily_rent, deposit, total_pay,
            receiver_name, receiver_phone, receiver_addr, tx, status, ctime, chain_order_id
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), %s)
        """, (
            item_db_id,
            user_id,
            item_publish_uid,
            rent_day,
            daily_rent,
            deposit,
            total_pay_show,
            receiver_name,
            receiver_phone,
            receiver_addr,
            tx_hash.hex(),
            chain_order_id
        ))
        db_conn.commit()
        return jsonify({"code": 0, "msg": "租赁订单创建成功，押金已支付", "tx_hash": tx_hash.hex()})
    except Exception as e:
        if db_conn:
            db_conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"code": -999, "msg": f"租赁失败：{str(e)}"})

# 我的订单
@app.route("/get_my_rent", methods=["GET"])
def get_my_rent():
    if "uid" not in session:
        return jsonify({"code":-1,"msg":"未登录","list":[]})
    uid = session["uid"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT r.id, r.rent_day, r.daily_rent, r.deposit, r.total_pay,
    r.receiver_name, r.receiver_phone, r.receiver_addr,
    r.tx, r.status, r.ctime, r.chain_order_id, i.title
    FROM rent r LEFT JOIN item i ON r.iid = i.id WHERE r.rent_uid = %s ORDER BY r.ctime DESC
    """, (uid,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    arr = []
    for row in rows:
        arr.append({
            "id": row[0], "rent_day": row[1], "daily_rent": row[2], "deposit": row[3], "total_pay": row[4],
            "receiver_name": row[5], "receiver_phone": row[6], "receiver_addr": row[7],
            "tx": row[8], "status": row[9], "ctime": str(row[10]), "chain_order_id": row[11], "title": row[12]
        })
    return jsonify({"code":0,"list":arr})

# 归还商品
@app.route("/return_goods", methods=["POST"])
def return_goods():
    try:
        if "uid" not in session:
            return jsonify({"code": -1, "msg": "请登录"})
        user_id = session["uid"]
        chain_order_id = int(request.form.get("chain_order_id"))
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT addr FROM user WHERE id=%s", (user_id,))
        user_wallet_res = cur.fetchone()
        cur.close()
        conn.close()
        if not user_wallet_res or not user_wallet_res[0]:
            return jsonify({"code": -1, "msg": "请绑定钱包"})
        user_wallet = user_wallet_res[0]
        user_pk = get_private_key_by_addr(user_wallet)
        if not user_pk:
            return jsonify({"code": -1, "msg": "无匹配私钥"})
        tx = rental_contract.functions.returnGoods(chain_order_id).build_transaction({
            "from": user_wallet,
            "nonce": w3.eth.get_transaction_count(user_wallet),
            "gas": 3000000,
            "gasPrice": w3.to_wei(20, "gwei")
        })
        signed_tx = w3.eth.account.sign_transaction(tx, user_pk)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        db_conn = get_conn()
        db_cur = db_conn.cursor()
        db_cur.execute("SELECT iid FROM rent WHERE chain_order_id=%s", (chain_order_id,))
        item_db_id = db_cur.fetchone()[0]
        db_cur.execute("SELECT chain_id FROM item WHERE id=%s", (item_db_id,))
        item_chain_id = db_cur.fetchone()[0]
        db_cur.execute("UPDATE item SET on_shelf=1 WHERE chain_id=%s", (item_chain_id,))
        db_cur.execute("UPDATE rent SET status=1 WHERE chain_order_id=%s", (chain_order_id,))
        db_conn.commit()
        db_cur.close()
        db_conn.close()
        return jsonify({"code": 0, "msg": "归还完成，押金已退回", "tx_hash": tx_hash.hex()})
    except Exception as e:
        return jsonify({"code": -999, "msg": f"归还失败：{str(e)}"})

# 获取全部商品列表
@app.route("/get_all_items")
def get_all_items():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        SELECT i.id, i.uid, i.title, i.item_desc, i.price, i.deposit, i.chain_id, i.create_time, i.on_shelf, u.name, i.img_cid,
        CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END AS is_rented
        FROM item i LEFT JOIN user u ON i.uid = u.id
        LEFT JOIN rent r ON i.id = r.iid AND r.status = 0
        ORDER BY i.create_time ASC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        data_list = []
        for row in rows:
            data_list.append({
                "db_id": row[0],
                "uid": row[1],
                "title": row[2],
                "desc": row[3],
                "daily_rent": row[4],
                "deposit": row[5],
                "chain_id": row[6],
                "create_time": str(row[7]),
                "on_shelf": row[8],
                "publisher_name": row[9],
                "img_cid": row[10],
                "is_rented": row[11]
            })
        return jsonify({"code": 0, "list": data_list})
    except Exception as e:
        return jsonify({"code": -1, "msg": str(e)})

# 获取登录用户信息
@app.route("/get_user_info")
def get_user_info():
    if "uid" not in session:
        return jsonify({"code":-1,"msg":"未登录","username":"","uid":0})
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT name FROM user WHERE id=%s", (session["uid"],))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return jsonify({"code":0,"username":row[0], "uid": session["uid"]})
        else:
            return jsonify({"code":-1,"msg":"用户不存在","username":"","uid":0})
    except Exception as e:
        return jsonify({"code":-1,"msg":str(e),"username":"","uid":0})

# 静态页面
@app.route("/<filename>")
def static_html(filename):
    allow_page = ["login.html", "register.html", "order.html"]
    if filename not in allow_page:
        return redirect("/login.html?err=请登录后访问页面")
    return send_from_directory("../frontend", filename)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)