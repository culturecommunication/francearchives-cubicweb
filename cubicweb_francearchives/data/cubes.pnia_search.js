/* global $ */

function checkDateRange(){
  const $form = $('#date-facet')
  var $mininput = $form.find('#date-min-input');
  var minvalue = parseInt($mininput.val())
  var $maxinput = $form.find('#date-max-input')
  var maxvalue = parseInt($maxinput.val())
  $maxinput.removeClass('error');

    if (minvalue && maxvalue) {
      if (minvalue > maxvalue){
          $maxinput.addClass('error');
          return false
      }
    }
    $form.submit()
}

function setUpDateMaxInput(){
  $('#date-max-input').bind('focus', function(){
    $(this).removeClass("error")
  });
}


$('document').ready(function () {
  setUpDateMaxInput()
})
