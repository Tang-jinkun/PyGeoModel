import "maplibre-gl/dist/maplibre-gl.css";
import "element-plus/dist/index.css";
import "./styles/app.css";

import ElementPlus from "element-plus";
import { createApp } from "vue";

import App from "./App.vue";

createApp(App).use(ElementPlus).mount("#app");
