// Auth bypassed for single-user setup — no sign-in required.

const _bypassUser = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Admin",
  email: "admin@localhost",
  emailVerified: true,
  image: null,
  createdAt: new Date(),
  updatedAt: new Date(),
  first_name: null,
  last_name: null,
};

export const auth = {
  api: {
    getSession: async () => ({
      session: { token: "bypass", userId: _bypassUser.id },
      user: _bypassUser,
    }),
    // Stub any other methods that might be called
    signIn: { email: async () => ({}), social: async () => ({}) },
    signUp: { email: async () => ({}) },
    signOut: async () => ({}),
  },
  $Infer: { Session: {} as any },
} as any;

export type Session = any;
