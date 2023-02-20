function copyUrl(event) {
  event.preventDefault();
  var copyText = document.getElementById("copylink");
  var inputc = document.body.appendChild(document.createElement("input"));
  inputc.value = copyText.href;
  inputc.select();
  document.execCommand("copy");
  inputc.parentNode.removeChild(inputc);

  // Display "link copied" for 5 seconds
  document.getElementById("tooltip-copylink").classList.remove("hidden");
  setTimeout(function() {
    document.getElementById("tooltip-copylink").classList.add("hidden");
  }, 5000);
  copyText.focus();

}
