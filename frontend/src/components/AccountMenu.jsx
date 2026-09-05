import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import Icon from "./Icon";

export default function AccountMenu({ user }) {
  const signOut = useMutation({
    mutationFn: api.signOut,

    onSettled: () => window.location.reload(),
  });

  if (!user) return null;

  return (
    <div className="account-menu" title={user.email}>
      <span className="account-email">{user.email}</span>
      <button
        className="logout-link"
        onClick={() => signOut.mutate()}
        disabled={signOut.isPending}
      >
        <Icon name="logout" size={13} />
        Sign out
      </button>
    </div>
  );
}
