"use client";

import { useCallback, useEffect, useId, useState } from "react";

import type { NotificationSettings, UpdateNotificationSettings } from "@shopping-assistant/api-client";

import { errorMessage, notificationSettings } from "@/lib/api";
import { fromNow } from "@/lib/format";

type Channel = NotificationSettings["channel"];

const CHANNELS: { value: Channel; label: string; help: string }[] = [
  { value: "console", label: "Console", help: "Printed in the terminal running the worker (or the API for test alerts)." },
  { value: "webhook", label: "Webhook", help: "Discord, Slack, Telegram or any URL that accepts JSON." },
  { value: "email", label: "Email", help: "Sent through the email service set up in source/.env." },
];

type Notice = { tone: "good" | "bad"; text: string } | null;

/**
 * Choose and test the alert channel (US-41). Server secrets never reach the browser: the
 * saved webhook URL comes back masked, and leaving the field empty keeps it.
 */
export function SettingsApp() {
  const ids = useId();
  const [current, setCurrent] = useState<NotificationSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [channel, setChannel] = useState<Channel>("console");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState<"save" | "test" | "reset" | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const show = useCallback((s: NotificationSettings) => {
    setCurrent(s);
    setChannel(s.channel);
    setWebhookUrl("");
    setEmail(s.alert_email ?? "");
  }, []);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        show(await notificationSettings.get());
      } catch (e) {
        setLoadError(errorMessage(e));
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [show]);

  async function act(kind: "save" | "test" | "reset", action: () => Promise<string>) {
    setBusy(kind);
    setNotice(null);
    try {
      setNotice({ tone: "good", text: await action() });
    } catch (e) {
      setNotice({ tone: "bad", text: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  function save(event: React.FormEvent) {
    event.preventDefault();
    const body: UpdateNotificationSettings = { channel };
    if (webhookUrl.trim()) body.webhook_url = webhookUrl.trim(); // empty = keep the saved URL
    if (channel === "email") body.alert_email = email.trim() || null;
    void act("save", async () => {
      show(await notificationSettings.save(body));
      return "Saved. The next price check uses these settings.";
    });
  }

  const test = () => act("test", async () => (await notificationSettings.test()).message);

  const reset = () =>
    act("reset", async () => {
      await notificationSettings.reset();
      show(await notificationSettings.get());
      return "Back to the settings in source/.env.";
    });

  if (loadError) {
    return (
      <p role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
        {loadError}
      </p>
    );
  }
  if (!current) return <p className="text-sm text-stone-500">Loading your settings…</p>;

  const dirty =
    channel !== current.channel || webhookUrl.trim() !== "" || (channel === "email" && email.trim() !== (current.alert_email ?? ""));

  return (
    <div className="max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-stone-600 dark:text-stone-400">Where price-drop alerts are sent.</p>
      </div>

      <form onSubmit={save} className="space-y-5 rounded-2xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900">
        <p className="text-sm text-stone-600 dark:text-stone-400">
          {current.source === "saved"
            ? `Using your saved settings${current.updated_at ? ` (updated ${fromNow(current.updated_at)})` : ""}.`
            : "Nothing saved yet: using NOTIFIER from source/.env."}
        </p>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-sm font-medium">Alert channel</legend>
          {CHANNELS.map((c) => {
            const unavailable = c.value === "email" && !current.email_available;
            return (
              <label
                key={c.value}
                className={`flex gap-3 rounded-xl border border-stone-200 p-3 text-sm has-checked:border-emerald-500 has-checked:bg-emerald-50/60 dark:border-stone-800 dark:has-checked:bg-emerald-950/30 ${
                  unavailable ? "opacity-60" : "cursor-pointer"
                }`}
              >
                <input
                  type="radio"
                  name="channel"
                  value={c.value}
                  checked={channel === c.value}
                  disabled={unavailable || busy !== null}
                  onChange={() => setChannel(c.value)}
                  className="mt-0.5 accent-emerald-600"
                />
                <span>
                  <span className="font-medium">{c.label}</span>
                  <span className="block text-stone-600 dark:text-stone-400">
                    {unavailable
                      ? "Not available: add ALERT_EMAIL_FROM and RESEND_API_KEY (or SMTP_HOST) to source/.env, then restart the API."
                      : c.help}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>

        {channel === "webhook" && (
          <div className="space-y-1">
            <label htmlFor={`${ids}-webhook`} className="text-sm font-medium">
              Webhook URL
            </label>
            <input
              id={`${ids}-webhook`}
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder={current.webhook_url_hint ? "Leave empty to keep the saved URL" : "https://discord.com/api/webhooks/…"}
              autoComplete="off"
              aria-describedby={`${ids}-webhook-help`}
              className="w-full rounded-lg border border-stone-300 bg-transparent px-3 py-2 text-sm dark:border-stone-700"
            />
            <p id={`${ids}-webhook-help`} className="text-xs text-stone-500 dark:text-stone-400">
              {current.webhook_url_hint ? (
                <>
                  Saved: <code className="font-mono">{current.webhook_url_hint}</code> (hidden because it contains a
                  secret token).{" "}
                </>
              ) : null}
              For Telegram use https://api.telegram.org/bot&lt;TOKEN&gt;/sendMessage?chat_id=&lt;CHAT_ID&gt;.
            </p>
          </div>
        )}

        {channel === "email" && (
          <div className="space-y-1">
            <label htmlFor={`${ids}-email`} className="text-sm font-medium">
              Send alerts to
            </label>
            <input
              id={`${ids}-email`}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              className="w-full rounded-lg border border-stone-300 bg-transparent px-3 py-2 text-sm dark:border-stone-700"
            />
          </div>
        )}

        {notice && (
          <p
            role={notice.tone === "bad" ? "alert" : "status"}
            className={`rounded-lg px-3 py-2 text-sm ${
              notice.tone === "good"
                ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100"
                : "bg-rose-50 text-rose-900 dark:bg-rose-950/40 dark:text-rose-100"
            }`}
          >
            {notice.text}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={busy !== null || !dirty}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy === "save" ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            onClick={test}
            disabled={busy !== null || dirty}
            title={dirty ? "Save first, then send a test" : undefined}
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium hover:bg-stone-100 disabled:opacity-50 dark:border-stone-700 dark:hover:bg-stone-800"
          >
            {busy === "test" ? "Sending…" : "Send test alert"}
          </button>
          {current.source === "saved" && (
            <button
              type="button"
              onClick={reset}
              disabled={busy !== null}
              className="rounded-lg px-4 py-2 text-sm font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-50 dark:text-stone-400 dark:hover:bg-stone-800"
            >
              Use .env settings instead
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
