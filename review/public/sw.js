self.addEventListener("push", (event) => {
  let message = { title: "புதிய செய்தி ஆய்வுக்கு", body: "ஒரு செய்தி உங்கள் ஒப்புதலுக்குக் காத்திருக்கிறது.", url: "/" };
  try { if (event.data) message = { ...message, ...event.data.json() }; } catch {}
  event.waitUntil(self.registration.showNotification(message.title, {
    body: message.body, icon: "/icon.svg", badge: "/icon.svg", tag: message.tag,
    data: { url: message.url }
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const path = String(event.notification.data?.url || "/");
  const target = new URL(path.startsWith("/") ? path : "/", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const open = windows.find((client) => new URL(client.url).origin === self.location.origin);
    if (open) { await open.focus(); open.navigate(target); }
    else await self.clients.openWindow(target);
  })());
});
