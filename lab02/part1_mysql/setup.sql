-- 实验二第一阶段：按实验手册建表。不会插入、删除或修改房源记录。
-- 在已连接的课程 MySQL 终端中执行；已有同名表不会被覆盖。
SHOW DATABASES;
USE smartpark_lab;
SHOW TABLES;

CREATE TABLE IF NOT EXISTS houseinfo (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增长主键',
    title VARCHAR(200) COMMENT '标题',
    house VARCHAR(50) COMMENT '楼盘',
    address VARCHAR(200) COMMENT '地址',
    struct VARCHAR(50) COMMENT '户型',
    area VARCHAR(20) COMMENT '建筑面积',
    floor VARCHAR(20) COMMENT '楼层',
    maketime VARCHAR(20) COMMENT '建造年代',
    price VARCHAR(20) COMMENT '每平方米单价'
) CHARACTER SET utf8mb4;

SHOW TABLES;
DESCRIBE houseinfo;
SELECT COUNT(*) AS before_count FROM houseinfo;
