export type UserRole = "researcher" | "reviewer" | "admin" | "compliance" | "viewer";

export type Permission = "canReview" | "canUpload" | "canExport" | "canAdmin";

const permissions: Record<Permission, UserRole[]> = {
  canReview: ["reviewer", "admin", "compliance"],
  canUpload: ["researcher", "reviewer", "admin"],
  canExport: ["researcher", "reviewer", "admin"],
  canAdmin: ["admin"]
};

export function hasPermission(role: UserRole, permission: Permission) {
  return permissions[permission].includes(role);
}

export const demoSession = {
  user: {
    name: "Local Researcher",
    role: "researcher" as UserRole
  }
};
