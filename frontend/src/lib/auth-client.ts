// Auth bypassed for single-user setup — no sign-in required.
const _bypassUser = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Admin",
  email: "admin@localhost",
  image: null,
};

export const useSession = () => ({
  data: {
    session: { token: "bypass" },
    user: _bypassUser,
  },
  isPending: false,
  error: null,
});

export const signIn = {
  email: async (_opts: any) => ({ data: null, error: null }),
  social: async (_opts: any) => ({ data: null, error: null }),
};

export const signOut = {
  async: async (_opts?: any) => {},
};

export const signUp = {
  email: async (_opts: any) => ({ data: null, error: null }),
};

// Keep a dummy export in case anything imports authClient directly.
export const authClient = null as any;
