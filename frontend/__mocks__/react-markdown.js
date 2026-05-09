// Mock pour Jest : react-markdown est ESM pur, non transpilé par défaut dans CRA.
module.exports = {
  __esModule: true,
  default: function ReactMarkdown() {
    return null;
  },
};
