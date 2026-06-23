import mysql.connector
from mysql.connector import errorcode

host = "localhost"
user = "root"
pwd = "09231121Yjy"
dbname = "rental"

create_db = f"CREATE DATABASE IF NOT EXISTS {dbname} DEFAULT CHARACTER SET utf8mb4;"

# 建表字典
tables = {
    "user": (
        "CREATE TABLE IF NOT EXISTS user ("
        "id INT PRIMARY KEY AUTO_INCREMENT,"
        "name VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',"
        "pwd VARCHAR(100) NOT NULL COMMENT '加密密码',"
        "mail VARCHAR(100) COMMENT '邮箱',"
        "addr VARCHAR(42) DEFAULT '' COMMENT '绑定MetaMask钱包地址'"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    ),
    "item": (
        "CREATE TABLE IF NOT EXISTS item ("
        "id INT PRIMARY KEY AUTO_INCREMENT,"
        "uid INT NOT NULL COMMENT '发布者用户id',"
        "title VARCHAR(100) NOT NULL COMMENT '物品名称',"
        "item_desc TEXT COMMENT '物品描述',"
        "price DECIMAL(12,4) NOT NULL COMMENT '日租金(wei)',"
        "deposit DECIMAL(12,4) NOT NULL COMMENT '押金(wei)',"
        "on_shelf TINYINT DEFAULT 1 COMMENT '1上架 0下架',"
        "chain_id INT NOT NULL COMMENT '合约内物品ID',"
        "rent_count INT DEFAULT 0 COMMENT '累计租赁次数',"
        "FOREIGN KEY fk_item_user(uid) REFERENCES user(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    ),
    "rent": (
        "CREATE TABLE IF NOT EXISTS rent ("
        "id INT PRIMARY KEY AUTO_INCREMENT,"
        "iid INT NOT NULL COMMENT '物品id',"
        "rent_uid INT NOT NULL COMMENT '租赁人id',"
        "own_uid INT NOT NULL COMMENT '发布者id',"
        "rent_day INT NOT NULL COMMENT '租赁天数',"
        "tx VARCHAR(100) NOT NULL COMMENT '租赁锁定押金交易哈希',"
        "status TINYINT NOT NULL COMMENT '0租赁中 1待发布者确认归还 2交易完成押金已退',"
        "ctime DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '租赁创建时间',"
        "FOREIGN KEY fk_rent_item(iid) REFERENCES item(id) ON DELETE CASCADE,"
        "FOREIGN KEY fk_rent_rentuser(rent_uid) REFERENCES user(id) ON DELETE CASCADE,"
        "FOREIGN KEY fk_rent_owner(own_uid) REFERENCES user(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    ),
    "refund": (
        "CREATE TABLE IF NOT EXISTS refund ("
        "id INT PRIMARY KEY AUTO_INCREMENT,"
        "rid INT NOT NULL COMMENT '关联租赁订单id',"
        "tx VARCHAR(100) NOT NULL COMMENT '退款链上交易哈希，核验押金是否退回',"
        "amount DECIMAL(12,4) NOT NULL COMMENT '退还押金金额(wei)',"
        "time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '退款时间',"
        "FOREIGN KEY fk_refund_rent(rid) REFERENCES rent(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    )
}

# 删表顺序：4张业务表
drop_order = ["refund", "rent", "item", "user"]

def init():
    try:
        cnx = mysql.connector.connect(host=host, user=user, password=pwd)
        cur = cnx.cursor()
        cur.execute(create_db)
        cur.execute(f"use {dbname}")

        # 临时关闭外键约束检测，彻底解决删表外键报错
        cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
        # 强制删除残留旧wallet表
        cur.execute("DROP TABLE IF EXISTS wallet;")
        print("旧数据表 wallet 已清理完成")

        # 按依赖顺序删除所有业务表
        for t in drop_order:
            cur.execute(f"DROP TABLE IF EXISTS {t};")
            print(f"数据表 {t} 已删除")

        # 重新创建全新数据表
        for t, sql in tables.items():
            cur.execute(sql)
            print(f"数据表 {t} 重建完成")

        # 恢复外键约束检测
        cur.execute("SET FOREIGN_KEY_CHECKS = 1;")

        cnx.commit()
        cur.close()
        cnx.close()
        print("✅ 数据库初始化全部完成，共4张表：user、item、rent、refund")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("❌ 错误：MySQL账号或密码不正确")
        else:
            print("❌ 数据库异常：", err)

# 获取数据库连接公共方法
def get_conn():
    return mysql.connector.connect(
        host=host,
        user=user,
        password=pwd,
        database=dbname
    )

if __name__ == "__main__":
    init()