var app = angular.module('[[module]]', []);
app.controller('[[controller]]', function($scope) {
    $scope.rows = [];
    $scope.errors = [];
    $scope.[[done_ids]] = [];
    $scope.message = '';
    $scope.refreshNote = '';
    $scope.loading = true;
    $scope.busy = false;
    var lastLoad = 0;
[[labels]]    var failed = function(data) {
        $scope.errors = (data && data.errors) || ['The tile could not reach its Python code.'];
        $scope.loading = false;
        $scope.busy = false;
    };
    var cohorts = function() {
        return $scope.rows.filter(function(row) { return !row.population; });
    };
    $scope.cohortCount = function() { return cohorts().length; };
    $scope.batchCount = function() {
        return cohorts().filter(function(row) { return row.submit; }).length;
    };
    $scope.populationNote = function() {
        var population = $scope.rows.filter(function(row) { return row.population; })[0];
        return (population && population.submit) ? '[[population_note]]' : '';
    };
    $scope.[[is_done]] = function(id) {
        return $scope.[[done_ids]].indexOf(parseInt(id, 10)) >= 0;
    };
    // "2026-11-25T10:00:00Z" -> "2026-11-25 10:00 UTC"
    $scope.when = function(text) {
        return text ? String(text).replace('T', ' ').replace(/:\d\dZ$/, ' UTC') : '';
    };
    // Rows the user has edited keep the edits; new cohorts are added, removed ones dropped.
    var merge = function(fresh) {
        var edited = {};
        $scope.rows.forEach(function(row) { if (row.dirty && !row.population) { edited[row.id] = row; } });
        // Only the ticks are kept: the status, build and [[done_noun]] times are always fresh.
        return fresh.map(function(row) {
            var mine = edited[row.id];
            return mine ? angular.extend(row, {submit: mine.submit, replace: mine.replace, dirty: true}) : row;
        });
    };
    $scope.load = function(keepEdits) {
        if ($scope.busy) { return; }
        $scope.busy = true;
        lastLoad = Date.now();
        $scope.callPythonDo({action: 'load'}).then(function(data) {
            if (!data.ok) { return failed(data); }
            var before = $scope.rows.length;
            $scope.rows = keepEdits ? merge(data.rows) : data.rows;
            $scope.[[done_ids]] = data.[[done_ids_key]] || [];
            $scope.refreshNote = (keepEdits && $scope.rows.length !== before) ? 'List updated with the cohorts built since.' : '';
            $scope.loading = false;
            $scope.busy = false;
        }, failed);
    };
    // Picks up cohorts built above: when the pointer comes back to this tile or the window regains
    // focus, at most every 3 seconds.
    $scope.refresh = function() {
        if (Date.now() - lastLoad > 3000) { $scope.load(true); }
    };
    var onFocus = function() { $scope.$apply($scope.refresh); };
    window.addEventListener('focus', onFocus);
    $scope.$on('$destroy', function() { window.removeEventListener('focus', onFocus); });
    $scope.save = function() {
        $scope.busy = true;
        $scope.message = '';
        $scope.callPythonDo({action: 'save', rows: $scope.rows}).then(function(data) {
            if (!data.ok) { return failed(data); }
            $scope.errors = [];
            $scope.message = data.saved + ' cohort(s) in the batch. Click "[[run_button]]" below to run it.';
            $scope.busy = false;
            $scope.load(false);
        }, failed);
    };
    $scope.load(false);
});
