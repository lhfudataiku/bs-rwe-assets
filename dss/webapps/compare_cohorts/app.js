// "Compare cohorts" standard webapp (solution-revision-plan.md R3, decisions 10, 12, 13).
// Lists the characterized cohorts, asks the backend for a pair, and polls until it is computed.
// The dashboard charts below read covariate_balance; the user then selects the pair in the page filter.
(function() {
    var cohort = document.getElementById('rwd-cohort');
    var comparator = document.getElementById('rwd-comparator');
    var button = document.getElementById('rwd-compare');
    var message = document.getElementById('rwd-message');
    var POLL_MS = 2000;

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
            el.selected = option.id === selected;
            select.appendChild(el);
        });
    }

    function show(answer) {
        say(answer.message, answer.state);
        if (answer.state === 'running') {
            setTimeout(function() {
                var query = '?cohort=' + encodeURIComponent(cohort.value) + '&comparator=' +
                    encodeURIComponent(comparator.value);
                call('/status' + query).then(show, unreachable);
            }, POLL_MS);
        } else {
            button.disabled = false;
        }
    }

    button.addEventListener('click', function() {
        button.disabled = true;
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
        say('', 'info');
    }, unreachable);
})();
