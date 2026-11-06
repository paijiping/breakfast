window.breakfastOrderSubmission = {
  async submit(order) {
    if (!order.table || !Array.isArray(order.items) || order.items.length === 0) {
      throw new Error("請確認桌號與餐點內容。");
    }

    await new Promise((resolve) => window.setTimeout(resolve, 450));

    const timeCode = Date.now().toString(36).slice(-5).toUpperCase();
    return {
      ok: true,
      demo: true,
      orderId: `DEMO-${timeCode}`,
      table: order.table
    };
  }
};