// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

contract CampusRental {
    struct Item {
        address owner;
        uint256 dailyRent;
        uint256 deposit;
        bool available;
    }

    struct Order {
        address renter;
        uint256 itemId;
        uint256 rentDays;
        bool finished;
    }

    Item[] public itemList;
    Order[] public orderList;

    //地址 => 自己发布的商品ID数组
    mapping(address => uint256[]) public userOwnedItems;

    //发布租赁物品（末尾新增记录商品ID到用户映射）
    function publishItem(uint256 dailyRent, uint256 deposit) external returns(uint256) {
        itemList.push(Item({
            owner: msg.sender,
            dailyRent: dailyRent,
            deposit: deposit,
            available: true
        }));
        uint256 newId = itemList.length - 1;
        userOwnedItems[msg.sender].push(newId);
        return newId;
    }

    //读取某用户全部自有商品ID
    function getUserAllItemIds(address user) external view returns(uint256[] memory) {
        return userOwnedItems[user];
    }

    //创建租赁订单：仅收取押金，租金前端仅展示，不链上转账
    function createRentOrder(uint256 itemId, uint256 rentDays) external payable {
        Item storage item = itemList[itemId];
        require(msg.sender != item.owner, unicode"不能租赁自己发布的商品");
        require(item.available, unicode"物品已被租赁");
        // 仅支付押金
        require(msg.value == item.deposit, unicode"押金金额不符");
        orderList.push(Order({
            renter: msg.sender,
            itemId: itemId,
            rentDays: rentDays,
            finished: false
        }));
        item.available = false;
    }

    //归还物品：只全额退还押金，不计算、不抵扣租金
    function returnGoods(uint256 orderId) external {
        Order storage order = orderList[orderId];
        require(!order.finished, unicode"订单已完成");
        require(order.renter == msg.sender, unicode"仅承租人可归还");

        Item storage item = itemList[order.itemId];
        // 直接全额退还押金
        (bool success, ) = payable(msg.sender).call{value: item.deposit}("");
        require(success, unicode"押金退还失败，合约余额不足");

        item.available = true;
        order.finished = true;
    }

    // 修改商品日租金、押金
    function updateItemPrice(uint256 itemId, uint256 newDaily, uint256 newDeposit) external {
        Item storage item = itemList[itemId];
        require(msg.sender == item.owner, unicode"仅商品所有者可修改价格");
        require(item.available == true, unicode"租赁中商品不可修改价格");
        item.dailyRent = newDaily;
        item.deposit = newDeposit;
    }

    // 获取物品总数
    function getItemCount() external view returns(uint256) {
        return itemList.length;
    }

    // 获取订单总数
    function getOrderCount() external view returns(uint256) {
        return orderList.length;
    }
}