const AppBarComp = {
    name: 'AppBarComp',
    template: '<div>APP BAR COMP</div>'
};

const AppFooComp = {
    name: 'AppFooComp',
    template: '<div>APP FOO COMP</div>',
    created: function() {
        this.$root.$on('test-clicked', function(ev) {
            console.log('[comp AppFooComp] listener for root "test-clicked", ev:', ev);
            // alert('catch root event test-clicked');
        });

    }
};

export { AppBarComp, AppFooComp };