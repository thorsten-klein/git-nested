// Shows GitHub alerts ('> [!NOTE]', '> [!TIP]', '> [!IMPORTANT]',
// '> [!WARNING]', '> [!CAUTION]') the way GitHub does.
// Sphinx renders them as a plain quote that starts with "[!NOTE]".
// This removes the marker and adds a label and the classes that
// custom.css colors.
document.addEventListener("DOMContentLoaded", function () {
  var marker = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/;
  // the icons GitHub uses
  var emoji = {
    note: "ℹ️",
    tip: "💡",
    important: "❗",
    warning: "⚠️",
    caution: "🛑",
  };

  document.querySelectorAll(".rst-content blockquote").forEach(function (blockquote) {
    var firstParagraph = blockquote.querySelector("p");
    var firstNode = firstParagraph && firstParagraph.firstChild;
    if (!firstNode || firstNode.nodeType !== Node.TEXT_NODE) {
      return;
    }

    var match = marker.exec(firstNode.textContent);
    if (!match) {
      return;
    }

    firstNode.textContent = firstNode.textContent.slice(match[0].length);

    var type = match[1].toLowerCase();
    blockquote.classList.add("alert", "alert-" + type);

    var title = document.createElement("span");
    title.className = "alert-title";
    title.textContent = emoji[type] + " " + type;
    firstParagraph.insertBefore(title, firstParagraph.firstChild);
    firstParagraph.insertBefore(document.createElement("br"), title.nextSibling);
  });
});
