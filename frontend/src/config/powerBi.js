/** Rapport publié sur Power BI Service (hedha howa.pbix). */

const DEFAULT_REPORT_ID = "69dc2b69-b15b-4f93-9823-d605bdd2ae5e";
const DEFAULT_VIEW_URL =
  "https://app.powerbi.com/groups/me/reports/69dc2b69-b15b-4f93-9823-d605bdd2ae5e?experience=power-bi";

const SUPERVISOR_PAGES = [
  {
    key: "ocr",
    label: "OCR & corrections",
    pageName: process.env.REACT_APP_POWERBI_SUPERVISOR_PAGE_3_NAME || "Page 3",
    pageId:
      process.env.REACT_APP_POWERBI_SUPERVISOR_PAGE_3_ID ||
      "95265ac3319c3eb069d9",
  },
  {
    key: "alerts",
    label: "Alertes & comptes PCG",
    pageName: process.env.REACT_APP_POWERBI_SUPERVISOR_PAGE_5_NAME || "Page 5",
    pageId:
      process.env.REACT_APP_POWERBI_SUPERVISOR_PAGE_5_ID ||
      "d7076eb25b057d6ac5a6",
  },
];

function workspaceId() {
  return process.env.REACT_APP_POWERBI_WORKSPACE_ID?.trim();
}

/** Rapport complet (admin). */
export function getAdminReportId() {
  return process.env.REACT_APP_POWERBI_REPORT_ID || DEFAULT_REPORT_ID;
}

/**
 * Rapport superviseur (recommandé : .pbix avec uniquement pages 3 et 5).
 * Sinon = même rapport que l’admin (il faut masquer les pages dans Power BI Desktop).
 */
export function getSupervisorReportId() {
  const dedicated = process.env.REACT_APP_POWERBI_SUPERVISOR_REPORT_ID?.trim();
  return dedicated || getAdminReportId();
}

export function usesDedicatedSupervisorReport() {
  return Boolean(process.env.REACT_APP_POWERBI_SUPERVISOR_REPORT_ID?.trim());
}

export function getSupervisorPages() {
  return SUPERVISOR_PAGES;
}

export function getPowerBiViewUrl(pageSegment, reportIdOverride) {
  const id = reportIdOverride || getAdminReportId();
  if (!pageSegment) {
    return (
      process.env.REACT_APP_POWERBI_VIEW_URL ||
      (id === DEFAULT_REPORT_ID
        ? DEFAULT_VIEW_URL
        : `https://app.powerbi.com/groups/me/reports/${id}?experience=power-bi`)
    );
  }
  return `https://app.powerbi.com/groups/me/reports/${id}/${pageSegment}?experience=power-bi`;
}

/**
 * @param {{ reportId?: string, pageId?: string, pageName?: string, hideNavigation?: boolean }} options
 */
export function buildPowerBiEmbedUrl(options = {}) {
  const {
    reportId: reportIdOpt,
    pageId,
    pageName,
    hideNavigation = false,
  } = options;

  const rid = reportIdOpt || getAdminReportId();

  const params = new URLSearchParams({
    reportId: rid,
    autoAuth: "true",
  });

  const ws = workspaceId();
  if (ws && ws !== "me") {
    params.set("groupId", ws);
  }

  const segment = pageId || pageName;
  if (segment) {
    if (segment.includes("-") && segment.length >= 32) {
      params.set("pageId", segment);
    } else {
      params.set("pageName", segment);
    }
  }

  const config = hideNavigation
    ? {
        navContentPaneEnabled: false,
        filterPaneEnabled: false,
        panes: {
          pageNavigation: { visible: false },
          filters: { expanded: false, visible: false },
        },
      }
    : {
        navContentPaneEnabled: true,
        filterPaneEnabled: false,
      };
  params.set("config", JSON.stringify(config));

  if (hideNavigation) {
    params.set("navContentPaneEnabled", "false");
    params.set("filterPaneEnabled", "false");
    params.set("pageNavigation", "false");
  }

  return `https://app.powerbi.com/reportEmbed?${params.toString()}`;
}

export function buildSupervisorEmbedUrl(page) {
  const dedicated = usesDedicatedSupervisorReport();
  return buildPowerBiEmbedUrl({
    reportId: getSupervisorReportId(),
    pageId: !dedicated && page.pageId ? page.pageId : undefined,
    pageName: dedicated || !page.pageId ? page.pageName : undefined,
    hideNavigation: true,
  });
}
