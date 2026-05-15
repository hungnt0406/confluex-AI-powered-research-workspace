"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

type NavSection = "profile" | "security" | "notifications" | "appearance" | "language" | "default-project" | "billing" | "credits";

interface ToggleProps {
  on: boolean;
  onChange: (value: boolean) => void;
  ariaLabel: string;
}

function Toggle({ on, onChange, ariaLabel }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={ariaLabel}
      onClick={() => onChange(!on)}
      className="relative shrink-0 w-9 h-5 rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      style={{ background: on ? "#32432c" : "#c4c8be" }}
    >
      <span
        className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-200"
        style={{ transform: on ? "translateX(16px)" : "translateX(0)" }}
      />
    </button>
  );
}

interface NavItemProps {
  icon: string;
  label: string;
  section: NavSection;
  active: boolean;
  onClick: (section: NavSection) => void;
}

function NavItem({ icon, label, section, active, onClick }: NavItemProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(section)}
      className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-[13px] cursor-pointer transition-colors text-left ${
        active
          ? "bg-primary/10 text-on-surface font-medium"
          : "text-on-surface-variant hover:bg-primary/[0.06] hover:text-on-surface"
      }`}
    >
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: "18px",
          color: active ? "#32432c" : undefined,
          fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20",
        }}
      >
        {icon}
      </span>
      {label}
    </button>
  );
}

interface ThemeCardProps {
  label: string;
  selected: boolean;
  preview: React.ReactNode;
  onClick: () => void;
}

function ThemeCard({ label, selected, preview, onClick }: ThemeCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl p-4 flex flex-col gap-2 text-left transition-all ${
        selected
          ? "bg-secondary-container"
          : "bg-surface-container-low hover:bg-surface-container"
      }`}
      style={selected ? { boxShadow: "inset 0 0 0 1.5px #32432c" } : { boxShadow: "inset 0 0 0 1px rgba(116,120,112,.28)" }}
      aria-pressed={selected}
    >
      {preview}
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-medium">{label}</p>
        {selected && (
          <span className="material-symbols-outlined text-primary" style={{ fontSize: "16px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}>
            check_circle
          </span>
        )}
      </div>
    </button>
  );
}

function ComingSoonPlaceholder({ title }: { title: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-outline/30 px-8 py-14 text-center">
      <span className="material-symbols-outlined text-hint" style={{ fontSize: "32px", fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24" }}>
        construction
      </span>
      <p className="mt-3 text-sm font-semibold text-on-surface">{title}</p>
      <p className="mt-1 text-xs text-on-surface-variant">This section is coming soon.</p>
    </div>
  );
}

interface ProfileFormState {
  fullName: string;
  displayName: string;
  email: string;
  affiliation: string;
  role: string;
  primaryField: string;
}

interface NotificationRow {
  id: string;
  label: string;
  description: string;
  email: boolean;
  inApp: boolean;
}

interface AppearanceState {
  theme: "light" | "dark" | "system";
  readingFont: string;
  baseTextSize: string;
  reduceMotion: boolean;
  inlineSourcePreviews: boolean;
  italicSerif: boolean;
}

function getInitials(email: string): string {
  const local = email.split("@")[0] ?? "";
  const parts = local.split(/[._-]/);
  if (parts.length >= 2) {
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

const ROLE_OPTIONS = ["Graduate student", "Undergraduate", "Postdoc", "Faculty", "Industry researcher", "Independent"];
const FIELD_OPTIONS = ["Computer Science — NLP", "Computer Science — ML", "Biomedical informatics", "Social sciences", "Humanities", "Other"];
const FONT_OPTIONS = ["Noto Serif (default)", "Inter", "Charter", "Atkinson Hyperlegible"];
const SIZE_OPTIONS = ["Compact (13px)", "Comfortable (14px)", "Spacious (15px)", "Large (16px)"];

const INITIAL_NOTIFICATIONS: NotificationRow[] = [
  { id: "deep-search", label: "Deep Search report finished", description: "When a multi-hop research run completes.", email: true, inApp: true },
  { id: "comments", label: "New comments in shared projects", description: "Lab / team comments on documents you authored.", email: true, inApp: true },
  { id: "digest", label: "Weekly reading digest", description: "New papers matching your saved searches.", email: true, inApp: false },
  { id: "usage", label: "Usage at 80% of plan", description: "Heads-up before you hit a Deep Search or PDF limit.", email: true, inApp: true },
  { id: "product", label: "Product updates from Confluex", description: "Occasional notes on new features. No marketing.", email: false, inApp: false },
];

const FIELD_INPUT_CLASS =
  "bg-white border border-outline-variant rounded-xl px-3 py-2.5 text-[13px] w-full focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary/10 transition-colors";

export default function SettingsPage() {
  const { ready, token, user } = useAuth();
  const router = useRouter();
  const [activeSection, setActiveSection] = useState<NavSection>("profile");

  const initials = user?.email ? getInitials(user.email) : "??";

  const [profile, setProfile] = useState<ProfileFormState>({
    fullName: "",
    displayName: "",
    email: user?.email ?? "",
    affiliation: "",
    role: ROLE_OPTIONS[0]!,
    primaryField: FIELD_OPTIONS[0]!,
  });

  const [appearance, setAppearance] = useState<AppearanceState>({
    theme: "light",
    readingFont: FONT_OPTIONS[0]!,
    baseTextSize: SIZE_OPTIONS[1]!,
    reduceMotion: false,
    inlineSourcePreviews: true,
    italicSerif: true,
  });

  const [notifications, setNotifications] = useState<NotificationRow[]>(INITIAL_NOTIFICATIONS);
  const [profileDirty, setProfileDirty] = useState(false);

  useEffect(() => {
    if (ready && !token) {
      router.replace("/login?next=%2Fsettings");
    }
  }, [ready, token, router]);

  useEffect(() => {
    if (user?.email) {
      setProfile((prev) => ({ ...prev, email: user.email ?? prev.email }));
    }
  }, [user?.email]);

  const handleProfileChange = (field: keyof ProfileFormState, value: string) => {
    setProfile((prev) => ({ ...prev, [field]: value }));
    setProfileDirty(true);
  };

  const handleProfileDiscard = () => {
    setProfile((prev) => ({ ...prev, fullName: "", displayName: "", affiliation: "" }));
    setProfileDirty(false);
  };

  const handleProfileSave = () => {
    setProfileDirty(false);
  };

  const toggleNotification = (id: string, channel: "email" | "inApp") => {
    setNotifications((prev) =>
      prev.map((row) => (row.id === id ? { ...row, [channel]: !row[channel] } : row)),
    );
  };

  const handleNavClick = (section: NavSection) => {
    if (section === "billing" || section === "credits") {
      router.push("/pricing");
      return;
    }
    setActiveSection(section);
  };

  if (!ready || !token) {
    return (
      <main className="flex h-screen items-center justify-center text-sm uppercase tracking-[0.2em] text-hint">
        Loading...
      </main>
    );
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col font-ui text-on-surface bg-background">
      <TopBar initials={initials} userEmail={user?.email ?? ""} />

      <div className="flex-1 grid min-h-0" style={{ gridTemplateColumns: "260px 1fr" }}>
        <SettingsNav activeSection={activeSection} onNavClick={handleNavClick} userEmail={user?.email ?? ""} />

        <main className="overflow-y-auto" style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(29,45,24,0.25) transparent" }}>
          <div className="max-w-[820px] mx-auto px-10 py-10 space-y-12">
            {activeSection === "profile" && (
              <ProfileSection
                initials={initials}
                userEmail={user?.email ?? ""}
                profile={profile}
                dirty={profileDirty}
                onFieldChange={handleProfileChange}
                onDiscard={handleProfileDiscard}
                onSave={handleProfileSave}
              />
            )}
            {activeSection === "appearance" && (
              <AppearanceSection
                state={appearance}
                onChange={(patch) => setAppearance((prev) => ({ ...prev, ...patch }))}
              />
            )}
            {activeSection === "notifications" && (
              <NotificationsSection rows={notifications} onToggle={toggleNotification} />
            )}
            {(activeSection === "security" || activeSection === "language" || activeSection === "default-project") && (
              <ComingSoonSection section={activeSection} />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function TopBar({ initials, userEmail }: { initials: string; userEmail: string }) {
  return (
    <header className="h-14 border-b border-outline/20 bg-background flex items-center px-4 gap-4 shrink-0">
      <Link href="/chat" className="flex items-center gap-2 no-underline">
        <svg viewBox="0 0 62 60" width="22" height="22" aria-hidden="true" fill="none">
          {["M 4,50 C 8,35 18,15 32,6", "M 14,53 C 19,37 30,17 45,8", "M 24,55 C 30,39 42,19 56,10",
            "M 33,54 C 40,41 51,24 58,20", "M 40,52 C 45,43 53,31 56,32"].map((d, i) => (
            <path key={i} d={d} stroke="#32432c" strokeWidth="1.6" strokeLinecap="round" />
          ))}
        </svg>
        <span className="font-semibold text-on-surface" style={{ letterSpacing: "-0.01em", fontFamily: "Inter, sans-serif" }}>
          confluex
        </span>
      </Link>
      <span className="text-on-surface-variant/40">/</span>
      <span className="text-sm text-on-surface-variant">Workspace</span>
      <span className="text-on-surface-variant/40">/</span>
      <span className="text-sm font-medium text-on-surface">Settings</span>

      <div className="ml-auto flex items-center gap-3">
        <Link
          href="/chat"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-on-surface-variant hover:text-on-surface hover:bg-surface-container/60 transition-colors no-underline"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>arrow_back</span>
          Back to research
        </Link>
        <div
          className="w-7 h-7 rounded-full bg-secondary-container flex items-center justify-center text-primary font-semibold text-[12px]"
          title={userEmail}
          aria-label={`Avatar for ${userEmail}`}
        >
          {initials}
        </div>
      </div>
    </header>
  );
}

function SettingsNav({
  activeSection,
  onNavClick,
  userEmail,
}: {
  activeSection: NavSection;
  onNavClick: (section: NavSection) => void;
  userEmail: string;
}) {
  return (
    <aside
      className="border-r border-outline/20 overflow-y-auto px-3 py-5"
      style={{ background: "rgba(244,243,241,0.4)", scrollbarWidth: "thin", scrollbarColor: "rgba(29,45,24,0.25) transparent" }}
    >
      <p className="font-headline text-[22px] px-3 mb-1">Settings</p>
      <p className="text-[11px] text-on-surface-variant px-3 italic">
        Workspace · {userEmail.split("@")[0] ?? ""}
      </p>

      <p className="text-[10px] font-bold text-hint tracking-[0.14em] uppercase px-3 mt-[18px] mb-1.5">Account</p>
      <NavItem icon="person" label="Profile" section="profile" active={activeSection === "profile"} onClick={onNavClick} />
      <NavItem icon="lock" label="Password & security" section="security" active={activeSection === "security"} onClick={onNavClick} />
      <NavItem icon="notifications" label="Notifications" section="notifications" active={activeSection === "notifications"} onClick={onNavClick} />

      <p className="text-[10px] font-bold text-hint tracking-[0.14em] uppercase px-3 mt-[18px] mb-1.5">Workspace</p>
      <NavItem icon="palette" label="Appearance" section="appearance" active={activeSection === "appearance"} onClick={onNavClick} />
      <NavItem icon="language" label="Language & region" section="language" active={activeSection === "language"} onClick={onNavClick} />
      <NavItem icon="folder_managed" label="Default project" section="default-project" active={activeSection === "default-project"} onClick={onNavClick} />

      <p className="text-[10px] font-bold text-hint tracking-[0.14em] uppercase px-3 mt-[18px] mb-1.5">Plan</p>
      <NavItem icon="receipt_long" label="Billing & plan" section="billing" active={activeSection === "billing"} onClick={onNavClick} />
      <NavItem icon="toll" label="Credits" section="credits" active={activeSection === "credits"} onClick={onNavClick} />
    </aside>
  );
}

function ProfileSection({
  initials,
  userEmail,
  profile,
  dirty,
  onFieldChange,
  onDiscard,
  onSave,
}: {
  initials: string;
  userEmail: string;
  profile: ProfileFormState;
  dirty: boolean;
  onFieldChange: (field: keyof ProfileFormState, value: string) => void;
  onDiscard: () => void;
  onSave: () => void;
}) {
  return (
    <>
      <header>
        <p className="text-[11px] tracking-[0.18em] uppercase font-semibold text-primary mb-2">Account</p>
        <h1 className="font-headline text-[36px] leading-tight">
          Your <em>profile</em>.
        </h1>
        <p className="text-[14px] text-on-surface-variant mt-2 max-w-[60ch]">
          How Confluex shows up for you, and how it shows you to collaborators on shared projects.
        </p>
      </header>

      <section
        className="rounded-2xl bg-surface-container-lowest"
        style={{ boxShadow: "inset 0 0 0 1px rgba(116,120,112,.28)" }}
      >
        <div className="px-7 py-6 flex items-center gap-5 border-b border-outline/15">
          <div className="w-16 h-16 rounded-full bg-secondary-container flex items-center justify-center text-primary font-headline text-[24px] shrink-0">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-headline text-[17px] truncate">{profile.fullName || userEmail}</p>
            <p className="text-[12px] text-on-surface-variant">{userEmail}</p>
          </div>
          <button
            type="button"
            className="text-[12px] px-3 py-1.5 rounded-full flex items-center gap-1.5 transition-colors hover:bg-surface-container"
            style={{ boxShadow: "inset 0 0 0 1px rgba(116,120,112,.28)" }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>photo_camera</span>
            Change photo
          </button>
          <button type="button" className="text-[12px] text-on-surface-variant hover:text-on-surface transition-colors">
            Remove
          </button>
        </div>

        <div className="px-7 py-6 grid grid-cols-2 gap-5">
          <FormField label="Full name">
            <input
              type="text"
              value={profile.fullName}
              onChange={(e) => onFieldChange("fullName", e.target.value)}
              className={FIELD_INPUT_CLASS}
              placeholder="Your full name"
            />
          </FormField>
          <FormField label="Display name" hint="Shown to collaborators in shared projects.">
            <input
              type="text"
              value={profile.displayName}
              onChange={(e) => onFieldChange("displayName", e.target.value)}
              className={FIELD_INPUT_CLASS}
              placeholder="Display name"
            />
          </FormField>
          <FormField label="Email">
            <input
              type="email"
              value={profile.email}
              onChange={(e) => onFieldChange("email", e.target.value)}
              className={FIELD_INPUT_CLASS}
            />
          </FormField>
          <FormField label="Affiliation">
            <input
              type="text"
              value={profile.affiliation}
              onChange={(e) => onFieldChange("affiliation", e.target.value)}
              className={FIELD_INPUT_CLASS}
              placeholder="Institution or organization"
            />
          </FormField>
          <FormField label="Role">
            <select
              value={profile.role}
              onChange={(e) => onFieldChange("role", e.target.value)}
              className={FIELD_INPUT_CLASS}
            >
              {ROLE_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
            </select>
          </FormField>
          <FormField label="Primary field">
            <select
              value={profile.primaryField}
              onChange={(e) => onFieldChange("primaryField", e.target.value)}
              className={FIELD_INPUT_CLASS}
            >
              {FIELD_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
            </select>
          </FormField>
        </div>

        <div
          className="px-7 py-4 flex items-center justify-between rounded-b-2xl"
          style={{ background: "rgba(239,238,236,0.4)", borderTop: "1px solid rgba(116,120,112,.15)" }}
        >
          <p className="text-[11px] text-on-surface-variant italic">
            {dirty ? "Unsaved changes" : "Changes auto-save"}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onDiscard}
              className="text-[12px] text-on-surface-variant px-3 py-1.5 hover:text-on-surface transition-colors"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={onSave}
              className="text-[12px] bg-primary text-white px-4 py-1.5 rounded-full hover:-translate-y-px transition-transform"
            >
              Save changes
            </button>
          </div>
        </div>
      </section>
    </>
  );
}

function FormField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[12px] font-semibold text-on-surface mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-on-surface-variant mt-1.5 italic">{hint}</p>}
    </div>
  );
}

function AppearanceSection({
  state,
  onChange,
}: {
  state: AppearanceState;
  onChange: (patch: Partial<AppearanceState>) => void;
}) {
  return (
    <>
      <header>
        <p className="text-[11px] tracking-[0.18em] uppercase font-semibold text-primary mb-2">Workspace</p>
        <h1 className="font-headline text-[36px] leading-tight">Appearance</h1>
        <p className="text-[14px] text-on-surface-variant mt-2">Tune the reading environment.</p>
      </header>

      <section
        className="rounded-2xl bg-surface-container-lowest px-7 py-6 space-y-6"
        style={{ boxShadow: "inset 0 0 0 1px rgba(116,120,112,.28)" }}
      >
        <div>
          <p className="text-[12px] font-semibold text-on-surface mb-3">Theme</p>
          <div className="grid grid-cols-3 gap-3">
            <ThemeCard
              label="Linen (light)"
              selected={state.theme === "light"}
              onClick={() => onChange({ theme: "light" })}
              preview={
                <div className="h-12 rounded-lg flex items-end p-1.5" style={{ background: "#faf9f7", boxShadow: "inset 0 0 0 1px rgba(116,120,112,.28)" }}>
                  <div className="h-1.5 rounded" style={{ width: "66%", background: "#32432c" }} />
                </div>
              }
            />
            <ThemeCard
              label="Forest (dark)"
              selected={state.theme === "dark"}
              onClick={() => onChange({ theme: "dark" })}
              preview={
                <div className="h-12 rounded-lg flex items-end p-1.5" style={{ background: "#1a1c1b" }}>
                  <div className="h-1.5 rounded" style={{ width: "66%", background: "#9cb092" }} />
                </div>
              }
            />
            <ThemeCard
              label="Match system"
              selected={state.theme === "system"}
              onClick={() => onChange({ theme: "system" })}
              preview={
                <div className="h-12 rounded-lg flex items-end p-1.5" style={{ background: "linear-gradient(to right, #faf9f7, #1a1c1b)" }}>
                  <div className="h-1.5 rounded" style={{ width: "66%", background: "#c4c8be" }} />
                </div>
              }
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-5">
          <FormField label="Reading font">
            <select
              value={state.readingFont}
              onChange={(e) => onChange({ readingFont: e.target.value })}
              className={FIELD_INPUT_CLASS}
            >
              {FONT_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
            </select>
          </FormField>
          <FormField label="Base text size">
            <select
              value={state.baseTextSize}
              onChange={(e) => onChange({ baseTextSize: e.target.value })}
              className={FIELD_INPUT_CLASS}
            >
              {SIZE_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
            </select>
          </FormField>
        </div>

        <div className="space-y-4 pt-5" style={{ borderTop: "1px solid rgba(116,120,112,.18)" }}>
          <ToggleRow
            label="Reduce motion"
            description="Skip transitions and parallax in the reading view."
            on={state.reduceMotion}
            onChange={(v) => onChange({ reduceMotion: v })}
          />
          <ToggleRow
            label="Show inline source previews"
            description="Hover a citation in chat to peek at the cited passage."
            on={state.inlineSourcePreviews}
            onChange={(v) => onChange({ inlineSourcePreviews: v })}
          />
          <ToggleRow
            label="Italic serif for key terms"
            description="A small editorial flourish in generated reports."
            on={state.italicSerif}
            onChange={(v) => onChange({ italicSerif: v })}
          />
        </div>
      </section>
    </>
  );
}

function ToggleRow({ label, description, on, onChange }: { label: string; description: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-6">
      <div>
        <p className="text-[13px] font-medium">{label}</p>
        <p className="text-[12px] text-on-surface-variant mt-0.5">{description}</p>
      </div>
      <Toggle on={on} onChange={onChange} ariaLabel={label} />
    </div>
  );
}

function NotificationsSection({
  rows,
  onToggle,
}: {
  rows: NotificationRow[];
  onToggle: (id: string, channel: "email" | "inApp") => void;
}) {
  return (
    <>
      <header>
        <p className="text-[11px] tracking-[0.18em] uppercase font-semibold text-primary mb-2">Account</p>
        <h1 className="font-headline text-[36px] leading-tight">Notifications</h1>
        <p className="text-[14px] text-on-surface-variant mt-2">Only what is worth interrupting you for.</p>
      </header>

      <section
        className="rounded-2xl bg-surface-container-lowest overflow-hidden"
        style={{ boxShadow: "inset 0 0 0 1px rgba(116,120,112,.28)" }}
      >
        <table className="w-full text-[13px]">
          <thead
            className="text-[11px] tracking-[0.14em] uppercase font-semibold text-on-surface-variant"
            style={{ background: "rgba(239,238,236,.5)" }}
          >
            <tr>
              <th className="text-left px-7 py-3">Event</th>
              <th className="text-center px-3 py-3 w-[120px]">Email</th>
              <th className="text-center px-3 py-3 w-[120px]">In-app</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline/15">
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="px-7 py-3.5">
                  <p className="font-medium">{row.label}</p>
                  <p className="text-[11px] text-on-surface-variant">{row.description}</p>
                </td>
                <td className="text-center">
                  <Toggle on={row.email} onChange={() => onToggle(row.id, "email")} ariaLabel={`${row.label} email notifications`} />
                </td>
                <td className="text-center">
                  <Toggle on={row.inApp} onChange={() => onToggle(row.id, "inApp")} ariaLabel={`${row.label} in-app notifications`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function ComingSoonSection({ section }: { section: NavSection }) {
  const titles: Record<NavSection, string> = {
    security: "Password & Security",
    language: "Language & Region",
    "default-project": "Default Project",
    profile: "Profile",
    notifications: "Notifications",
    appearance: "Appearance",
    billing: "Billing & Plan",
    credits: "Credits",
  };

  return (
    <>
      <header>
        <h1 className="font-headline text-[36px] leading-tight">{titles[section]}</h1>
      </header>
      <ComingSoonPlaceholder title={titles[section]} />
    </>
  );
}
