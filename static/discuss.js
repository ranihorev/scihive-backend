function renderComments() {
  var root = d3.select("#discussion");
  var n = comments.length;
  if(n === 0) { root.append('div').html('none, so far.'); }
  for(var i=0;i<n;i++) {
    // show the comment
    var c = comments[i];
    if(typeof c.text === 'undefined') { var text = ''; } else { var text = c.text; }
    var time_text = timeConverter(c.time_posted);
    var cdiv = root.append('div').classed('comment', true);
    // add action items
    cdiv.append('div').classed('caction', true)
        .append('a').attr('href', 'discuss?id='+gpid+'&cid='+c._id)
        .append('img').attr('src', 'static/linkto.png').attr('alt', 'link to this comment');
    // header information: user/time/version
    var cdiv_header = cdiv.append('div').classed('cheader', true);
    if(typeof cid_highlight !== 'undefined' && cid_highlight === c._id) {
      cdiv_header.attr('style', 'background-color:#ff0'); // highlight this comment specifically
      node_scroll_to = cdiv_header[0][0]; // raw dom element
    }
    cdiv_header.append('div').classed('cuser', true).html('@'+c.user);
    cdiv_header.append('div').classed('ctime', true).html(time_text);
    cdiv_header.append('div').classed('cver', true).html('v'+c.version);
    cdiv_header.append('div').classed('cconf', true).html(c.conf);
    // actual comment
    cdiv.append('div').classed('ctext', true).html(marked(text));
    // tags
    var cdiv_tags = cdiv.append('div').classed('ctags', true);
    // error div
    var cerr = cdiv.append('div').classed('cerr', true); // hidden initially
    // now insert tags into tags div
    for(var j=0,m=tags.length;j<m;j++) {
      var tag_count = tag_counts[i][j];
      var cdiv_tag_count = cdiv_tags.append('div').classed('ctag-count', true).html(tag_count);
      if(tag_count === 0) { cdiv_tag_count.classed('ctag-count-zero', true); }
      var cdiv_tag = cdiv_tags.append('div').classed('ctag', true).html(tags[j]);
      // attach a click handler
      cdiv_tag.on('click', function(elt, celt, cid, errelt){return function(){
        // inform the server with a POST request
        var request_data = {}
        request_data.tag_name = elt.html();
        request_data.comment_id = cid;
        request_data.pid = gpid;
        $.post("/toggletag", request_data).done(function(data){
          if(data != 'OK') { errelt.html(data); }
          else {
            // toggle the visual state
            var is_active = !elt.classed('ctag-active');
            elt.classed('ctag-active', is_active);
            // also (de/in)crement the count
            var new_count = parseInt(celt.html()) + (is_active ? 1.0 : -1.0);
            if(new_count < 0) { new_count = 0; } // should never happen
            celt.html(new_count);
          }
        });
      }}(cdiv_tag, cdiv_tag_count, c._id, cerr));
    }
  }
}

var prev_txt = '';
function renderPost() {
  var txt = $("#post-text").val(); // raw text of textarea contents
  if(txt === prev_txt) { return; } // break out early, no changes from before.
  prev_txt = txt;

  console.log('rendering preview...');
  $("#preview-wrap").slideDown("fast");

  // render to html with marked
  var html = marked(txt);
  // insert into preview div
  $("#preview").html(html);
  // fire off a request to process any latex
  if (typeof MathJax !== 'undefined') { MathJax.Hub.Queue(["Typeset",MathJax.Hub]); }
}

function doPost() {
  // lets put together a POST request to submit a new post in the discussion.
  var txt = $("#post-text").val();
  // do some checks etc
  if(txt.length <= 5) {
    $("#errors-etc").html('Post is too short. Come on, what are you doing?').slideDown("fast");
    return;
  }
  if(txt.length > 10000) {
    $("#errors-etc").html('Post is too long! What are you doing?').slideDown("fast");
    return;
  }

  var conf = '';
  var sel = document.querySelector('input[name="conf"]:checked');
  if(sel !== null) { conf = sel.value; }

  var anon = 0;
  var sel = document.querySelector('input[name="anon"]:checked');
  if(sel !== null) { anon = 1; }

  var request_data = {}
  request_data.text = txt;
  request_data.conf = conf;
  request_data.anon = anon;
  request_data.pid = gpid;
  console.log('request data:');
  console.log(request_data);

  $.post("/comment", request_data)
   .done(function(data){
      // toggle state of the image to reflect the state of the server, as reported by response
      if(data === 'OK') {
        $("#errors-etc").html('Posted!').slideDown("fast");
        setInterval(function(){location.reload(false);}, 1000);
      } else {
        $("#errors-etc").html(data).slideDown("fast");
      }
   })
   .fail(function(xhr, status, error) {
      console.log(xhr);
      console.log(status);
      console.log(error);
      $("#errors-etc").html('Request failed, sorry. See console to maybe debug.').slideDown("fast");
   });
}

// when page loads...
$(document).ready(function(){

  cid_highlight = QueryString.cid;

  // display message, if any
  if(msg !== '') { d3.select("#rtable").append('div').classed('msg', true).html(msg); }
  // display the subject-of-disussion paper on top
	addPapers(1, false);
  // display the comments
  renderComments();

  // click on Pitch in! call for action toggle expansion of comment textarea etc
  $("#pitchin-cfa").click(function() {
    $("#pitchin").slideToggle("fast", function() { });
  });

  $("#btnpost").click(function(){
    doPost();
  })
  // periodically try to render a preview of the post
  setInterval(renderPost, 250);

  // scroll to a comment if any
  if(typeof node_scroll_to !== 'undefined') {
    $('html, body').animate({
        scrollTop: $(node_scroll_to).offset().top
    }, 1000);
  }
});
