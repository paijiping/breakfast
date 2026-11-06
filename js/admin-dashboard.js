((root) => {
  const taiwanOffset = 8 * 60 * 60 * 1000;
  const dayMilliseconds = 24 * 60 * 60 * 1000;

  function calculateRevenue(orders, now = new Date()) {
    const nowTime = now.getTime();
    const localNow = new Date(nowTime + taiwanOffset);
    const year = localNow.getUTCFullYear();
    const month = localNow.getUTCMonth();
    const day = localNow.getUTCDate();
    const today = Date.UTC(year, month, day);
    const weekStart = today - ((localNow.getUTCDay() + 6) % 7) * dayMilliseconds;
    const monthStart = Date.UTC(year, month, 1);
    const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const periods = {
      day: { total: 0, buckets: Array.from({ length: 24 }, (_, hour) => ({ label: `${String(hour).padStart(2, "0")}:00`, amount: 0 })) },
      week: { total: 0, buckets: Array.from({ length: 7 }, (_, index) => {
        const date = new Date(weekStart + index * dayMilliseconds);
        return { label: `${date.getUTCMonth() + 1}/${date.getUTCDate()}`, amount: 0 };
      }) },
      month: { total: 0, buckets: Array.from({ length: daysInMonth }, (_, index) => ({ label: `${index + 1}日`, amount: 0 })) }
    };

    for (const order of orders) {
      const timestamp = Date.parse(order.created_at);
      if (order.status !== "completed" || !Number.isFinite(timestamp) || timestamp > nowTime) continue;
      const localTime = timestamp + taiwanOffset;
      const amount = Number(order.total_amount);
      if (!Number.isFinite(amount)) continue;
      if (localTime >= today) {
        periods.day.buckets[Math.floor((localTime - today) / (60 * 60 * 1000))].amount += amount;
        periods.day.total += amount;
      }
      if (localTime >= weekStart) {
        periods.week.buckets[Math.floor((localTime - weekStart) / dayMilliseconds)].amount += amount;
        periods.week.total += amount;
      }
      if (localTime >= monthStart) {
        periods.month.buckets[Math.floor((localTime - monthStart) / dayMilliseconds)].amount += amount;
        periods.month.total += amount;
      }
    }
    return periods;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { calculateRevenue };
  else root.AdminDashboard = { calculateRevenue };
})(globalThis);