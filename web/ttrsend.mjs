// 📤 Send to TTR: opens Andrew's TTR app in a new tab and hands it the orders that were read; TTR's 📥 Import AliExpress
// orders pop-up opens with them (nothing is added until Import is pressed there). TTR is only reachable on his own
// devices (Tailscale), so for anyone else the tab just doesn't load. Shift+click the button to change the TTR address.
// Handshake: TTR (once its data has loaded) posts {type:"ttr-ready"} to the tab that opened it; this page answers with
// {type:"aliexpress-orders", file, orders} to that exact origin only; TTR answers {type:"ttr-got", n}.

export const TTR_DEFAULT = "https://ttr.testtagrepair.co.nz";
export const ttrUrl = () => { try { return localStorage.getItem("aer-ttr-url") || TTR_DEFAULT; } catch { return TTR_DEFAULT; } };

export function sendToTtr(res, say, changeAddress = false) {
  let url = ttrUrl();
  if (changeAddress) {
    const v = prompt("Your TTR address (as you open it in the browser):", url);
    if (!v) return;
    try { url = new URL(v.trim()).origin; } catch { alert("That isn't a web address."); return; }
    try { localStorage.setItem("aer-ttr-url", url); } catch {}
  }
  if (!res || !res.orders || !res.orders.length) { say("Open a PDF first."); return; }
  const origin = new URL(url).origin;
  const w = window.open(origin + "/", "ttr-aliexpress");
  if (!w) { say("⚠ The browser blocked the new tab: allow pop-ups for this page, then 📤 again."); return; }
  say("📤 Opening your TTR… log in there if it asks.");
  const payload = {type: "aliexpress-orders", v: 1, file: res.file, orders: res.orders};
  let done = false;
  const onMsg = e => {
    if (e.source !== w || e.origin !== origin || !e.data) return;
    if (e.data.type === "ttr-ready" && !done) w.postMessage(payload, origin);
    if (e.data.type === "ttr-got") {
      done = true;
      window.removeEventListener("message", onMsg);
      say(`📤 Sent ${e.data.n} orders to TTR: tick and press 📥 Import in the TTR tab.`);
    }
  };
  window.addEventListener("message", onMsg);
  setTimeout(() => {
    if (done) return;
    window.removeEventListener("message", onMsg);
    say(`⚠ TTR didn't answer. Is ${origin} open and logged in (and Tailscale on)? Shift+click 📤 to change the address.`);
  }, 180000);
}
