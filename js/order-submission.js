window.breakfastOrderSubmission = {
  async submit(order) {
    if (!order.table || !Array.isArray(order.items) || order.items.length === 0) {
      throw new Error("請確認桌號與餐點內容。");
    }

    const response = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        table: order.table,
        items: order.items.map(({ id, quantity, note }) => ({ id, quantity, note }))
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "訂單送出失敗，請稍後重試。");
    return result;
  }
};