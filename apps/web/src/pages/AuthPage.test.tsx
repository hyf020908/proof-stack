import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { useAuthStore } from "../auth/store";
import { renderPage } from "../test/utils";
import { AuthPage } from "./AuthPage";

const user = {
  id: "user-1",
  organization_id: "org-1",
  email: "owner@example.test",
  display_name: "Ada Reviewer",
  role: "owner" as const,
  is_active: true,
};

describe("AuthPage", () => {
  it("validates the login form before calling the API", async () => {
    const login = vi.spyOn(api.auth, "login");
    renderPage(<AuthPage mode="login" />, ["/login"]);
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeVisible();
    expect(screen.getByText("Password must contain at least 8 characters.")).toBeVisible();
    expect(login).not.toHaveBeenCalled();
  });

  it("stores a successful session and returns to the requested page", async () => {
    vi.spyOn(api.auth, "login").mockResolvedValue({
      access_token: "access",
      refresh_token: "refresh",
      user,
    });
    renderPage(
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/" element={<div>Protected destination</div>} />
      </Routes>,
      ["/login"],
    );
    await userEvent.type(screen.getByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "Strong-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(useAuthStore.getState().accessToken).toBe("access"));
  });

  it("supports one-click local demo login", async () => {
    vi.spyOn(api.auth, "demo").mockResolvedValue({
      access_token: "demo-access",
      refresh_token: "demo-refresh",
      user,
    });
    renderPage(
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/" element={<div>Demo workspace</div>} />
      </Routes>,
      ["/login"],
    );
    await userEvent.click(screen.getByRole("button", { name: /enter the demo workspace/i }));
    await waitFor(() => expect(useAuthStore.getState().accessToken).toBe("demo-access"));
  });
});
