var app = angular.module('built_cohorts', []);
app.controller('BuiltCohortsController', function($scope) {
    $scope.rows = [];
    $scope.errors = [];
    $scope.loading = true;
    $scope.load = function() {
        $scope.callPythonDo({}).then(function(data) {
            $scope.rows = data.ok ? data.rows : [];
            $scope.errors = data.ok ? [] : data.errors;
            $scope.loading = false;
        }, function(data) {
            $scope.errors = (data && data.errors) || ['The tile could not reach its Python code.'];
            $scope.loading = false;
        });
    };
    $scope.load();
});
