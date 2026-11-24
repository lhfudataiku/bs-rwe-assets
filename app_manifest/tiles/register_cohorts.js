var app = angular.module('register_cohorts', []);
app.controller('RegisterCohortsController', function($scope) {
    $scope.rows = [];
    $scope.errors = [];
    $scope.writtenIds = [];
    $scope.message = '';
    $scope.refreshNote = '';
    $scope.loading = true;
    $scope.busy = false;
    var lastLoad = 0;
    var labels = {'new': 'New', 'pending': 'In batch, not written', 'registered': 'Written', 'changed': 'Changed since written'};
    var failed = function(data) {
        $scope.errors = (data && data.errors) || ['The tile could not reach its Python code.'];
        $scope.loading = false;
        $scope.busy = false;
    };
    $scope.statusLabel = function(row) {
        var label = labels[row.status] || row.status;
        return (row.status === 'registered' || row.status === 'changed') ? label + ' as cohort ' + row.id : label;
    };
    $scope.batchCount = function() {
        return $scope.rows.filter(function(row) { return row.submit; }).length;
    };
    $scope.isWritten = function(id) {
        return $scope.writtenIds.indexOf(parseInt(id, 10)) >= 0;
    };
    // Text areas grow with their text: about 40 characters a line, up to 8 lines.
    $scope.lines = function(text, least) {
        return Math.min(8, Math.max(least, Math.ceil(((text || '').length + 1) / 40)));
    };
    // Rows the user has edited keep the edits; new scripts are added, deleted ones dropped.
    var merge = function(fresh) {
        var edited = {};
        $scope.rows.forEach(function(row) { if (row.dirty) { edited[row.file] = row; } });
        return fresh.map(function(row) { return edited[row.file] || row; });
    };
    $scope.load = function(keepEdits) {
        if ($scope.busy) { return; }
        $scope.busy = true;
        lastLoad = Date.now();
        $scope.callPythonDo({action: 'load'}).then(function(data) {
            if (!data.ok) { return failed(data); }
            var before = $scope.rows.length;
            $scope.rows = keepEdits ? merge(data.rows) : data.rows;
            $scope.writtenIds = data.registered_ids || [];
            $scope.refreshNote = (keepEdits && $scope.rows.length !== before) ? 'List updated with the scripts uploaded above.' : '';
            $scope.loading = false;
            $scope.busy = false;
        }, failed);
    };
    // Picks up scripts uploaded above: when the pointer comes back to this tile or the window
    // regains focus (the upload dialog closing), at most every 3 seconds.
    $scope.refresh = function() {
        if (Date.now() - lastLoad > 3000) { $scope.load(true); }
    };
    var onFocus = function() { $scope.$apply($scope.refresh); };
    window.addEventListener('focus', onFocus);
    $scope.$on('$destroy', function() { window.removeEventListener('focus', onFocus); });
    $scope.register = function() {
        $scope.busy = true;
        $scope.message = '';
        $scope.callPythonDo({action: 'save', rows: $scope.rows}).then(function(data) {
            if (!data.ok) { return failed(data); }
            $scope.errors = [];
            $scope.message = data.saved + ' cohort(s) in the batch. Click "Write batch to cohort definition" below to write them.';
            $scope.busy = false;
            $scope.load(false);
        }, failed);
    };
    $scope.load(false);
});
