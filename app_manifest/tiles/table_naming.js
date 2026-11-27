var app = angular.module('table_naming', []);
app.controller('TableNamingController', function($scope) {
    $scope.s = {naming: 'atlas', prefix: '', mapping: {}};
    $scope.choices = [];
    $scope.groups = [];
    $scope.errors = [];
    $scope.status = '';
    $scope.loading = true;
    $scope.examples = {
        atlas: 'scripts exported from OHDSI Atlas: @cdm_database_schema.person, @vocabulary_database_schema.concept, @target_database_schema.@target_cohort_table',
        plain: 'bare table names: person, concept, cohort',
        prefix: 'the same prefix before every table: cdm.person, cdm.concept',
        mapping: 'each table named its own way, typed in a table below'
    };
    var atlas = {};
    var timer = null;
    var failed = function(data) {
        $scope.errors = (data && data.errors) || ['The tile could not reach its Python code.'];
        $scope.status = '';
        $scope.loading = false;
    };
    var hasMapping = function() {
        return Object.keys($scope.s.mapping).some(function(k) { return ($scope.s.mapping[k] || '').trim(); });
    };
    var save = function() {
        $scope.status = 'Saving…';
        $scope.callPythonDo({action: 'save', naming: $scope.s.naming, prefix: $scope.s.prefix,
                             mapping: $scope.s.mapping}).then(function(data) {
            if (!data.ok) { return failed(data); }
            $scope.errors = [];
            $scope.status = 'Saved.';
        }, failed);
    };
    // Saves on every change, half a second after the last keystroke; nothing to click.
    $scope.changed = function() {
        if ($scope.s.naming === 'mapping' && !hasMapping()) { angular.extend($scope.s.mapping, atlas); }
        $scope.status = '';
        if (timer) { clearTimeout(timer); }
        timer = setTimeout(function() { $scope.$apply(save); }, 500);
    };
    $scope.callPythonDo({action: 'load'}).then(function(data) {
        if (!data.ok) { return failed(data); }
        atlas = data.atlas;
        $scope.choices = data.choices;
        $scope.groups = data.groups;
        $scope.s = {naming: data.naming, prefix: data.prefix, mapping: angular.copy(data.mapping)};
        $scope.loading = false;
    }, failed);
});
