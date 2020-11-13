function initGlossary() {
  var sidebar = new StickySidebar(".glossary-alphabet-sticky", {
    topSpacing: 20,
    bottomSpacing: 20,
    containerSelector: ".glossary-content",
    innerWrapperSelector: ".glossary-alphabet",
  });
  return sidebar;
}

$("document").ready(function () {
  initGlossary();
});
