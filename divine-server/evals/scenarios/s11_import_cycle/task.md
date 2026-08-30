这个项目现在 `import orders` 或 `import payments` 都会报 ImportError（循环导入）。
请修复，要求：orders 和 payments 两个模块都能正常导入，
Order 默认状态是 PaymentStatus.PENDING，Payment 构造后 order 属性指向传入的订单。
totals.py 是无关模块，它的行为不要动。
