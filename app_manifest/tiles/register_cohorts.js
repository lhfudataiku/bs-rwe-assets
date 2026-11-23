var app = angular.module('register_cohorts', []);
app.controller('RegisterCohortsController', function($scope) {
    $scope.rows = [];
    $scope.errors = [];
    $scope.registeredIds = [];
    $scope.message = '';
    $scope.loading = true;
    $scope.busy = false;
    var labels = {'new': 'New', 'registered': 'Registered', 'changed': 'Changed since registration', 'pending': 'Submitted, not ingested'};
    var failed = function(data) {
        $scope.errors = (data && data.errors) || ['The tile could not reach its Python code.'];
        $scope.loading = false;
        $scope.busy = false;
    };
    $scope.statusLabel = function(row) {
        var label = labels[row.status] || row.status;
        return (row.status === 'registered' || row.status === 'changed') ? label + ' as cohort ' + row.id : label;
    };
    $scope.isRegistered = function(id) {
        return $scope.registeredIds.indexOf(parseInt(id, 10)) >= 0;
    };
    $scope.load = function() {
        $scope.busy = true;
        $scope.message = '';
        $scope.callPythonDo({action: 'load'}).then(function(data) {
            if (!data.ok) { return failed(data); }
            $scope.rows = data.rows;
            $scope.registeredIds = data.registered_ids || [];
            $scope.errors = [];
            $scope.loading = false;
            $scope.busy = false;
        }, failed);
    };
    $scope.save = function() {
        $scope.busy = true;
        $scope.message = '';
        $scope.callPythonDo({action: 'save', rows: $scope.rows}).then(function(data) {
            if (!data.ok) { return failed(data); }
            $scope.errors = [];
            $scope.message = data.saved + ' cohort(s) saved. Run "Ingest registered cohorts" below to register them.';
            $scope.busy = false;
        }, failed);
    };
    $scope.load();
});
