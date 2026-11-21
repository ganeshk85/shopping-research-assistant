import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NotificationSettings } from "@shopping-assistant/api-client";

import { SettingsApp } from "./settings-app";

const notificationSettings = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), reset: vi.fn(), test: vi.fn() }));

vi.mock("@/lib/api", () => ({
  notificationSettings,
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : "Something went wrong."),
}));

const ENV: NotificationSettings = {
  channel: "console", source: "env", webhook_url_hint: null, alert_email: null, email_available: false, updated_at: null,
};
const SAVED_WEBHOOK: NotificationSettings = {
  ...ENV, channel: "webhook", source: "saved", webhook_url_hint: "https://discord.com/…abcd", updated_at: new Date().toISOString(),
};

beforeEach(() => vi.clearAllMocks());

describe("SettingsApp (US-41)", () => {
  it("shows the channel in use and that .env applies", async () => {
    notificationSettings.get.mockResolvedValue(ENV);
    render(<SettingsApp />);
    expect(await screen.findByRole("radio", { name: /Console/ })).toBeChecked();
    expect(screen.getByText(/using NOTIFIER from source\/.env/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Email/ })).toBeDisabled(); // the server can't send email
    expect(screen.queryByRole("button", { name: /Use .env/ })).not.toBeInTheDocument();
  });

  it("saves a webhook and shows only the masked URL afterwards", async () => {
    notificationSettings.get.mockResolvedValue(ENV);
    notificationSettings.save.mockResolvedValue(SAVED_WEBHOOK);
    render(<SettingsApp />);
    await userEvent.click(await screen.findByRole("radio", { name: /Webhook/ }));
    await userEvent.type(screen.getByLabelText("Webhook URL"), "https://discord.com/api/webhooks/1/SECRET-abcd");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(notificationSettings.save).toHaveBeenCalledWith({
      channel: "webhook", webhook_url: "https://discord.com/api/webhooks/1/SECRET-abcd",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    expect(screen.getByLabelText("Webhook URL")).toHaveValue("");
    expect(screen.getByText("https://discord.com/…abcd")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("SECRET");
  });

  it("keeps the saved webhook when the field is left empty", async () => {
    notificationSettings.get.mockResolvedValue({ ...SAVED_WEBHOOK, channel: "console" });
    notificationSettings.save.mockResolvedValue(SAVED_WEBHOOK);
    render(<SettingsApp />);
    await userEvent.click(await screen.findByRole("radio", { name: /Webhook/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(notificationSettings.save).toHaveBeenCalledWith({ channel: "webhook" });
  });

  it("shows a validation error from the server", async () => {
    notificationSettings.get.mockResolvedValue(ENV);
    notificationSettings.save.mockRejectedValue(new Error("Enter a webhook URL to use webhook alerts."));
    render(<SettingsApp />);
    await userEvent.click(await screen.findByRole("radio", { name: /Webhook/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a webhook URL");
  });

  it("saves an email address when the server can send email", async () => {
    notificationSettings.get.mockResolvedValue({ ...ENV, email_available: true });
    notificationSettings.save.mockResolvedValue({ ...ENV, channel: "email", source: "saved", alert_email: "me@example.com", email_available: true });
    render(<SettingsApp />);
    await userEvent.click(await screen.findByRole("radio", { name: /Email/ }));
    await userEvent.type(screen.getByLabelText("Send alerts to"), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(notificationSettings.save).toHaveBeenCalledWith({ channel: "email", alert_email: "me@example.com" });
  });

  it("sends a test alert and shows success or the error", async () => {
    notificationSettings.get.mockResolvedValue(SAVED_WEBHOOK);
    notificationSettings.test
      .mockResolvedValueOnce({ channel: "webhook", message: "Test alert sent to your webhook." })
      .mockRejectedValueOnce(new Error("The test alert couldn't be delivered: 404 Not Found"));
    render(<SettingsApp />);
    const button = await screen.findByRole("button", { name: "Send test alert" });
    await userEvent.click(button);
    expect(await screen.findByRole("status")).toHaveTextContent("Test alert sent to your webhook.");
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("404 Not Found");
  });

  it("asks to save before testing unsaved changes", async () => {
    notificationSettings.get.mockResolvedValue(ENV);
    render(<SettingsApp />);
    await userEvent.click(await screen.findByRole("radio", { name: /Webhook/ }));
    expect(screen.getByRole("button", { name: "Send test alert" })).toBeDisabled();
  });

  it("can go back to the .env settings", async () => {
    notificationSettings.get.mockResolvedValueOnce(SAVED_WEBHOOK).mockResolvedValueOnce(ENV);
    notificationSettings.reset.mockResolvedValue(undefined);
    render(<SettingsApp />);
    await userEvent.click(await screen.findByRole("button", { name: "Use .env settings instead" }));
    expect(notificationSettings.reset).toHaveBeenCalled();
    expect(await screen.findByRole("radio", { name: /Console/ })).toBeChecked();
  });
});
