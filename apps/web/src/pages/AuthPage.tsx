import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FlaskConical, GitPullRequest, ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { api } from "../api/client";
import type { AuthTokens } from "../api/types";
import { useAuthStore } from "../auth/store";
import { AuthLayout } from "../components/AppShell";
import { Button } from "../components/ui";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Password must contain at least 8 characters."),
});

const registerSchema = loginSchema.extend({
  display_name: z.string().trim().min(2, "Enter at least 2 characters.").max(80),
  organization_name: z.string().trim().min(2, "Enter at least 2 characters.").max(100),
  password: z
    .string()
    .min(12, "Use at least 12 characters.")
    .regex(/[A-Z]/, "Include an uppercase letter.")
    .regex(/[a-z]/, "Include a lowercase letter.")
    .regex(/[0-9]/, "Include a number."),
});

type AuthFields = z.infer<typeof registerSchema>;

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useAuthStore((state) => state.setSession);
  const accessToken = useAuthStore((state) => state.accessToken);
  const destination =
    (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/";
  const isRegister = mode === "register";

  useEffect(() => {
    if (accessToken) void navigate(destination, { replace: true });
  }, [accessToken, destination, navigate]);

  const form = useForm<AuthFields>({
    resolver: zodResolver(isRegister ? registerSchema : loginSchema),
    defaultValues: {
      email: "",
      password: "",
      display_name: "",
      organization_name: "",
    },
  });

  const completeLogin = async (tokens: AuthTokens) => {
    setSession(tokens);
    if (!tokens.user) {
      const user = await api.auth.me();
      useAuthStore.getState().setUser(user);
    }
    void navigate(destination, { replace: true });
  };

  const submit = useMutation({
    mutationFn: async (values: AuthFields) => {
      if (isRegister) return api.auth.register(values);
      return api.auth.login(values.email, values.password);
    },
    onSuccess: (tokens) => void completeLogin(tokens),
  });

  const demo = useMutation({
    mutationFn: api.auth.demo,
    onSuccess: (tokens) => void completeLogin(tokens),
  });

  const error = submit.error ?? demo.error;

  return (
    <AuthLayout>
      <main className="auth-grid">
        <section className="auth-story" aria-labelledby="auth-story-title">
          <p className="eyebrow">Acceptance, made explainable</p>
          <h1 id="auth-story-title">A calm decision layer between generated code and merge.</h1>
          <p>
            ProofStack connects requirements, changed symbols, validation, security findings, and
            policy decisions into one auditable chain of evidence.
          </p>
          <div className="auth-story__proofs">
            <div className="proof-chip proof-chip--one">
              <GitPullRequest size={17} />
              <span>Change parsed</span>
              <CheckCircle2 size={15} />
            </div>
            <div className="proof-chip proof-chip--two">
              <ShieldCheck size={17} />
              <span>Security evidence</span>
              <strong>3</strong>
            </div>
            <div className="proof-chip proof-chip--three">
              <FlaskConical size={17} />
              <span>Validation</span>
              <strong>Warn</strong>
            </div>
          </div>
          <p className="auth-story__note">
            Offline-first analysis · Deterministic verdicts · Portable evidence bundles
          </p>
        </section>

        <section className="auth-panel glass-card" aria-labelledby="auth-title">
          <div className="auth-panel__heading">
            <p className="eyebrow">{isRegister ? "Create a workspace" : "Welcome back"}</p>
            <h2 id="auth-title">{isRegister ? "Start building proof" : "Sign in to ProofStack"}</h2>
            <p>
              {isRegister
                ? "Your first organization and owner account are created together."
                : "Continue to your evidence workspace."}
            </p>
          </div>

          <form
            className="form-stack"
            onSubmit={(event) => void form.handleSubmit((values) => submit.mutate(values))(event)}
            noValidate
          >
            {isRegister ? (
              <div className="field-row">
                <label className="field">
                  <span>Display name</span>
                  <input autoComplete="name" {...form.register("display_name")} />
                  {form.formState.errors.display_name ? (
                    <small role="alert">{form.formState.errors.display_name.message}</small>
                  ) : null}
                </label>
                <label className="field">
                  <span>Organization</span>
                  <input autoComplete="organization" {...form.register("organization_name")} />
                  {form.formState.errors.organization_name ? (
                    <small role="alert">{form.formState.errors.organization_name.message}</small>
                  ) : null}
                </label>
              </div>
            ) : null}
            <label className="field">
              <span>Email</span>
              <input type="email" autoComplete="email" {...form.register("email")} />
              {form.formState.errors.email ? (
                <small role="alert">{form.formState.errors.email.message}</small>
              ) : null}
            </label>
            <label className="field">
              <span>Password</span>
              <input
                type="password"
                autoComplete={isRegister ? "new-password" : "current-password"}
                {...form.register("password")}
              />
              {form.formState.errors.password ? (
                <small role="alert">{form.formState.errors.password.message}</small>
              ) : null}
            </label>

            {error ? (
              <div className="form-error" role="alert">
                {error.message}
              </div>
            ) : null}

            <Button type="submit" loading={submit.isPending} className="button--wide">
              {isRegister ? "Create workspace" : "Sign in"}
              <ArrowRight size={16} />
            </Button>
          </form>

          <div className="auth-divider">
            <span>or explore locally</span>
          </div>
          <Button
            variant="secondary"
            className="button--wide"
            loading={demo.isPending}
            onClick={() => demo.mutate()}
          >
            <FlaskConical size={17} />
            Enter the demo workspace
          </Button>
          <p className="auth-switch">
            {isRegister ? "Already have an account?" : "New to ProofStack?"}{" "}
            <Link to={isRegister ? "/login" : "/register"}>
              {isRegister ? "Sign in" : "Create a workspace"}
            </Link>
          </p>
        </section>
      </main>
    </AuthLayout>
  );
}
