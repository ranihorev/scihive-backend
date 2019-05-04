function populateList(lstid, msg, lst) {

  var div = d3.select('#'+lstid);
  var n = lst.length;
  div.append('div').classed('userlst-title', true).html(n + msg);
  if(n === 0) {
    var fd = div.append('div').classed('user-li', true).html('None so far.');
    fd.classed('li-no-border', true);
  } else {
    for(var i=0;i<n;i++) {
      var f = lst[i];

      var fd = div.append('div').classed('user-li', true);
      if(f.active === 1){ fd.classed('li-active', true);
      } else { fd.classed('li-inactive', true); }

      var fdx = fd.append('div').classed('fdx', true).html('X');

      // attach event handler to X, to remove this user
      var jfd = $(fd.node());
      var jfdx = $(fdx.node());
      var request_data = { user:f.user, lst:lstid };
      jfdx.on('click', function(rootnode, jdict) {
        return function() {
          $.post("/removefollow", jdict).done(function(elt){
            return function(data){
              if(data === 'OK') { elt.slideUp('fast'); } // remove the element from the UI
            }
          }(rootnode));
        }
      }(jfd, request_data));

      // attach an event handler to OK, allow this user to follow me
      if(lstid === 'followers' && f.active == 0) {
        var fdok = fd.append('div').classed('fdok', true).html('OK');
        var jfdok = $(fdok.node());
        var request_data = { user:f.user, lst:lstid };
        jfdok.on('click', function(rootnode, oknode, jdict) {
          return function() {
            $.post("/addfollow", jdict).done(function(elt, elt2){ // dont think closure in closure is necessary here, being lazy
              return function(data){
                if(data === 'OK') {
                  // ok we can follow this user
                  elt.classed('li-active', true);
                  elt.classed('li-inactive', false);
                  elt2.remove(); // take out the OK button.
                }
              }
            }(rootnode, oknode));
          }
        }(fd, fdok, request_data));
      }

      // // attach an event handler to OK, allow this user to follow me
      // if(lstid === 'followers') {
      //   if(f.active === 1) {
      //     // people who follow us (display an X)
      //   } else {
      //     // people who asked to follow us (display an X and a OK)
      //   }
      // } else if(lstid === 'following') {
      //   if(f.active === 1) {
      //     // people who we follow (display an X)
      //   } else {
      //     // people who we asked to follow but they didnt confirom (display an X)
      //   }
      // }

      // attach the actual username of the person
      var fdu = fd.append('div').classed('fdu', true).html(f.user);

      if(i === n-1) { fd.classed('li-no-border', true); }
    }
  }
}

// when page loads...
$(document).ready(function(){
  populateList('followers', ' followers:', followers);
  populateList('following', ' following:', following);
});
