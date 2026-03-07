import { createRouter, createWebHistory } from "vue-router";
import OverviewPage from "../pages/OverviewPage.vue";
import AnalysisPage from "../pages/AnalysisPage.vue";
import RulesPage from "../pages/RulesPage.vue";
import UploadPage from "../pages/UploadPage.vue";

const routes = [
  { path: "/", name: "overview", component: OverviewPage },
  { path: "/analysis", name: "analysis", component: AnalysisPage },
  { path: "/rules", name: "rules", component: RulesPage },
  { path: "/upload", name: "upload", component: UploadPage },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
