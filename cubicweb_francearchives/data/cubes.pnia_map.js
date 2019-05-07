/* global $, location, BASE_URL */
$.fn.dptMap = function(options) {
    var $form = $('#'+this.data('formid'));
    var hasOwnProperty = Object.prototype.hasOwnProperty;
    $form.submit(function(ev) {
        ev.preventDefault();
    });
    $form.find('input').hide();
    var $list = $('#service-listing'),
        $select = $('select[name="dpt"]'),
        loading = $('<img src="' + BASE_URL + 'data/loading.gif" />');

    var pathRE = /annuaire\/departements\/(\d+[AB]?)/,
        searchRe = /\?dpt=(\d+[AB]?)/;
    var selected = (function() {
        var m = pathRE.exec(location.pathname);
        if (m != null) {
            return m[1];
        }
        m = searchRe.exec(location.search);
        if (m != null) {
            return m[1];
        }
        return null;
    })();

    $select.change(function() {
        var code = $(this).val();
        if (options.urls === undefined) {
            $('#jqvmap1_' + code).trigger('click');
        } else {
            if (hasOwnProperty.call(options.urls, code)) {
                document.location.href = options.urls[code];
            }
        }
    });
    var defaultParams = {
        map: 'limite-dpt',
        enableZoom: false,
        showTooltip: true,
        backgroundColor: '#fff',
        borderColor: '#333',
        selectedRegions: selected,
        urls: null,
        onRegionClick: function onRegionClick(ev, code, region) {
            if (hasOwnProperty.call(options, 'disabledRegions') &&
                  (options.disabledRegions.indexOf(code) > -1 )) {
                    ev.preventDefault();
                    return;
            }
            if (options.urls === undefined) {
                document.location.href=BASE_URL + 'annuaire/departements?dpt=' + code;
                $select.val(code.toUpperCase());
            }
            else {
                if (hasOwnProperty.call(options.urls, code)) {
                    document.location.href = options.urls[code];
                    $select.val(code.toUpperCase());
                }
            }
        }
    };
    $.extend(defaultParams, options|| {});
    this.vectorMap(defaultParams);
};
