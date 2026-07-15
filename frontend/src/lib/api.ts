export {
  API_BASE,
  assetUrl,
  getActiveUserId,
  setActiveUserId,
} from "@/lib/api/core";

import { adminApi } from "@/lib/api/admin";
import { mediaApi } from "@/lib/api/media";
import { productionApi } from "@/lib/api/production";
import { projectsApi } from "@/lib/api/projects";

export const api = {
  ...adminApi,
  ...projectsApi,
  ...mediaApi,
  ...productionApi,
};
