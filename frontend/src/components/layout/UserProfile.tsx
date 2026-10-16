"use client";
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { authApi, clearTokens, getAccessToken, UserResponse } from "@/lib/api";

export const UserProfile: React.FC = () => {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    if (!getAccessToken()) return;
    authApi
      .me()
      .then((res) => setUser(res.data))
      .catch(() => setUser(null));
  }, []);

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      // ignore network errors
    } finally {
      clearTokens();
      router.push("/login");
    }
  };

  const displayName = user?.full_name || "Enterprise User";
  const displayRole = (user?.role || "STUDENT").toUpperCase();
  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="border-t border-slate-200 p-3.5 bg-slate-50/60">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-700 shrink-0">
            {initials || <User size={14} />}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-900 truncate leading-tight">
              {displayName}
            </p>
            <p className="text-[10px] text-slate-500 font-medium tracking-wide mt-0.5">
              {displayRole}
            </p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer shrink-0"
          title="Sign out"
          aria-label="Sign out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </div>
  );
};

export default UserProfile;
