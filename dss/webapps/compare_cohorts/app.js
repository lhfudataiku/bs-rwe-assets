// "Compare cohorts" standard webapp (solution-revision-plan.md R3, decisions 10, 12, 13; step 4 part 6).
// Lists the characterized cohorts, asks the backend for a pair, and polls until it is computed and the
// dashboard's page 2 datasets are rebuilt. Inside the dashboard it follows the page filters (DSS sends
// them as `message` events) and, once a pair is ready, reloads the page with the filters set to that
// pair (the `pageFilters` URL parameter of DSS dashboards).
(function() {
    var cohort = document.getElementById('rwd-cohort');
    var comparator = document.getElementById('rwd-comparator');
    var button = document.getElementById('rwd-compare');
    var message = document.getElementById('rwd-message');
    var showLink = document.getElementById('rwd-show');
    var POLL_MS = 2000;
    var pageSelection = {};  // {cohort, comparator}: the values the page filters show, when known
    var loaded = false;

    function say(text, state) {
        message.textContent = text;
        message.className = 'rwd-message rwd-' + (state || 'info');
    }

    function call(path, options) {
        return fetch(getWebAppBackendUrl(path), options).then(function(response) {
            if (!response.ok) { throw new Error('the backend answered ' + response.status); }
            return response.json();
        });
    }

    function unreachable(e) {
        say('The comparison service is not running (' + e.message + '). The precomputed comparisons ' +
            'against the population are still shown below.', 'failed');
        button.disabled = false;
    }

    function fill(select, options, selected) {
        select.innerHTML = '';
        options.forEach(function(option) {
            var el = document.createElement('option');
            el.value = option.id;
            el.textContent = option.label;
            el.dataset.filter = option.filter || '';
            el.selected = option.id === selected;
            select.appendChild(el);
        });
    }

    function filterOf(select) {
        var el = select.options[select.selectedIndex];
        return el ? el.dataset.filter : undefined;
    }

    function choose(select, value) {
        for (var i = 0; i < select.options.length; i++) {
            if (value !== undefined && select.options[i].dataset.filter === value) {
                select.selectedIndex = i;
                return;
            }
        }
    }

    // The single selected value of a page filter on `column`, from DSS's filters message. Its schema is
    // not documented, so any object naming the column with selected values is accepted.
    function selectedValue(node, column) {
        if (!node || typeof node !== 'object') { return undefined; }
        if (node.column === column || node.columnName === column) {
            var picked = node.selectedValues || node.values;
            if (Array.isArray(picked) && picked.length === 1) { return String(picked[0]); }
            if (picked && !Array.isArray(picked) && typeof picked === 'object') {
                var keys = Object.keys(picked).filter(function(k) { return picked[k]; });
                if (keys.length === 1) { return keys[0]; }
            }
        }
        var children = Array.isArray(node) ? node : Object.keys(node).map(function(k) { return node[k]; });
        for (var i = 0; i < children.length; i++) {
            var found = selectedValue(children[i], column);
            if (found !== undefined) { return found; }
        }
        return undefined;
    }

    function followPage() {
        if (!loaded) { return; }
        choose(cohort, pageSelection.cohort);
        choose(comparator, pageSelection.comparator);
    }

    window.addEventListener('message', function(event) {
        if (!event.data || event.data.type !== 'filters') { return; }
        pageSelection = {cohort: selectedValue(event.data.filters, 'cohort'),
                         comparator: selectedValue(event.data.filters, 'comparator')};
        followPage();
    });

    // The dashboard page's URL with its filters set to the pair; null outside a dashboard.
    function pairUrl(filters) {
        var base;
        try { base = window.top.location.href; } catch (e) { base = document.referrer; }
        if (!base || base === window.location.href) { return null; }
        var hashAt = base.indexOf('#');
        var hash = hashAt < 0 ? '' : base.slice(hashAt);
        var url = hashAt < 0 ? base : base.slice(0, hashAt);
        var queryAt = url.indexOf('?');
        var path = queryAt < 0 ? url : url.slice(0, queryAt);
        var kept = queryAt < 0 ? [] : url.slice(queryAt + 1).split('&').filter(function(p) {
            return p && p.indexOf('pageFilters=') !== 0;
        });
        // Encoded as DSS documents it, parentheses included.
        kept.push('pageFilters=' + encodeURIComponent(filters).replace(/\(/g, '%28').replace(/\)/g, '%29'));
        return path + '?' + kept.join('&') + hash;
    }

    function showPair(answer) {
        var shown = pageSelection.cohort === filterOf(cohort) && pageSelection.comparator === filterOf(comparator);
        if (shown) { return; }  // the page already shows this pair
        var url = pairUrl(answer.page_filters);
        if (!url) { return; }
        showLink.href = url;
        showLink.hidden = false;
        try {
            window.top.location.assign(url);
        } catch (e) {
            // The dashboard does not let the tile navigate it: the link stays for the user.
        }
    }

    function show(answer) {
        say(answer.message, answer.state);
        if (answer.state === 'running') {
            setTimeout(function() {
                var query = '?cohort=' + encodeURIComponent(cohort.value) + '&comparator=' +
                    encodeURIComponent(comparator.value);
                call('/status' + query).then(show, unreachable);
            }, POLL_MS);
            return;
        }
        button.disabled = false;
        if ((answer.state === 'done' || answer.state === 'cached') && answer.page_filters) {
            showPair(answer);
        }
    }

    button.addEventListener('click', function() {
        button.disabled = true;
        showLink.hidden = true;
        say('Checking the pair...', 'running');
        call('/request', {method: 'POST', headers: {'Content-Type': 'application/json'},
                          body: JSON.stringify({cohort: cohort.value, comparator: comparator.value})})
            .then(show, unreachable);
    });

    call('/choices').then(function(data) {
        if (data.state !== 'ok') { return show(data); }
        if (!data.cohorts.length) {
            say('No cohort is characterized yet. Characterize cohorts in Project Setup first.', 'invalid');
            button.disabled = true;
            return;
        }
        fill(cohort, data.cohorts, data.cohorts[0].id);
        fill(comparator, data.comparators, data.default_comparator);
        loaded = true;
        followPage();
        say('', 'info');
    }, unreachable);
})();
