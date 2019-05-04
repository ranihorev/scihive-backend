// various JS utilities shared by all templates

// helper function so that we can access keys in url bar
var QueryString = function () {
  // This function is anonymous, is executed immediately and 
  // the return value is assigned to QueryString!
  var query_string = {};
  var query = window.location.search.substring(1);
  var vars = query.split("&");
  for (var i=0;i<vars.length;i++) {
    var pair = vars[i].split("=");
        // If first entry with this name
    if (typeof query_string[pair[0]] === "undefined") {
      query_string[pair[0]] = decodeURIComponent(pair[1]);
        // If second entry with this name
    } else if (typeof query_string[pair[0]] === "string") {
      var arr = [ query_string[pair[0]],decodeURIComponent(pair[1]) ];
      query_string[pair[0]] = arr;
        // If third or later entry with this name
    } else {
      query_string[pair[0]].push(decodeURIComponent(pair[1]));
    }
  }
    return query_string;
}();

function jq( myid ) { return myid.replace( /(:|\.|\[|\]|,)/g, "\\$1" ); } // for dealing with ids that have . in them

function updateQueryStringParameter(uri, key, value) {
  var re = new RegExp("([?&])" + key + "=.*?(&|$)", "i");
  var separator = uri.indexOf('?') !== -1 ? "&" : "?";
  if (uri.match(re)) {
    return uri.replace(re, '$1' + key + "=" + value + '$2');
  }
  else {
    return uri + separator + key + "=" + value;
  }
}

function build_ocoins_str(p) {
  var ocoins_info = {
    "ctx_ver": "Z39.88-2004",
    "rft_val_fmt": "info:ofi/fmt:kev:mtx:journal",
    "rfr_id": "info:sid/arxiv-sanity.com:arxiv-sanity",

    "rft_id": p.link,
    "rft.atitle": p.title,
    "rft.jtitle": "arXiv:" + p.pid + " [" + p.category.substring(0, p.category.indexOf('.')) + "]",
    "rft.date": p.published_time,
    "rft.artnum": p.pid,
    "rft.genre": "preprint",

    // NB: Stolen from Dublin Core; Zotero understands this even though it's
    // not part of COinS
    "rft.description": p.abstract,
  };
  ocoins_info = $.param(ocoins_info);
  ocoins_info += "&" + $.map(p.authors, function(a) {
      return "rft.au=" + encodeURIComponent(a);
    }).join("&");

  return ocoins_info;
}

function build_authors_html(authors) {
  var res = '';
  for(var i=0,n=authors.length;i<n;i++) {
    var link = '/search?q=' + authors[i].replace(/ /g, "+");
    res += '<a href="' + link + '">' + authors[i] + '</a>';
    if(i<n-1) res += ', ';
  }
  return res;
}

function build_categories_html(tags) {
  var res = '';
  for(var i=0,n=tags.length;i<n;i++) {
    var link = '/search?q=' + tags[i].replace(/ /g, "+");
    res += '<a href="' + link + '">' + tags[i] + '</a>';
    if(i<n-1) res += ' | ';
  }
  return res;
}

function strip_version(pidv) {
  var lst = pidv.split('v');
  return lst[0];
}

// populate papers into #rtable
// we have some global state here, which is gross and we should get rid of later.
var pointer_ix = 0; // points to next paper in line to be added to #rtable
var showed_end_msg = false;
function addPapers(num, dynamic) {
  if(papers.length === 0) { return true; } // nothing to display, and we're done

  var root = d3.select("#rtable");
  var twtr_score_field = window.location.pathname.includes('oldhype') ? 'hype_score' : (QueryString.age_decay === '1' ? 'twtr_score_dec' : 'twtr_score');

  var base_ix = pointer_ix;
  for(var i=0;i<num;i++) {
    var ix = base_ix + i;
    if(ix >= papers.length) {
      if(!showed_end_msg) {
        if (ix >= numresults){
          var msg = 'Results complete.';
        } else {
          var msg = 'You hit the limit of number of papers to show in one result.';
        }
        root.append('div').classed('msg', true).html(msg);
        showed_end_msg = true;
      }
      break;
    }
    pointer_ix++;

    var p = papers[ix];
    var div = root.append('div').classed('apaper', true).attr('id', p.pid);

    // Generate OpenURL COinS metadata element -- readable by Zotero, Mendeley, etc.
    var ocoins_span = div.append('span').classed('Z3988', true).attr('title', build_ocoins_str(p));

    var tdiv = div.append('div').classed('paperdesc', true);
    tdiv.append('span').classed('ts', true).append('a').attr('href', p.link).attr('target', '_blank').html(p.title);
    tdiv.append('br');
    tdiv.append('span').classed('as', true).html(build_authors_html(p.authors));
    tdiv.append('br');
    tdiv.append('span').classed('ds', true).html(p.published_time);
    if(p.originally_published_time !== p.published_time) {
      tdiv.append('span').classed('ds2', true).html('(v1: ' + p.originally_published_time + ')');
    }
    tdiv.append('span').classed('cs', true).html(build_categories_html(p.tags));
    tdiv.append('br');
    tdiv.append('span').classed('ccs', true).html(p.comment);

    // action items for each paper
    var ldiv = div.append('div').classed('dllinks', true);
    // show raw arxiv id
    ldiv.append('span').classed('spid', true).html(p.pid);
    // access PDF of the paper
    var pdf_link = p.link.replace("abs", "pdf"); // convert from /abs/ link to /pdf/ link. url hacking. slightly naughty
    if(pdf_link === p.link) { var pdf_url = pdf_link } // replace failed, lets fall back on arxiv landing page
    else { var pdf_url = pdf_link + '.pdf'; }
    ldiv.append('a').attr('href', pdf_url).attr('target', '_blank').html('pdf');
    
    // rank by tfidf similarity
    ldiv.append('br');
    var score = p[twtr_score_field] || 0;
    ldiv.append('span').html('Score: ' + score.toFixed(1));
//    var similar_span = ldiv.append('span').classed('sim', true).attr('id', 'sim'+p.pid).html('show similar');
//    similar_span.on('click', function(pid){ // attach a click handler to redirect for similarity search
//      return function() { window.location.replace('/' + pid); }
//    }(p.pid)); // closer over the paper id

    // var review_span = ldiv.append('span').classed('sim', true).attr('style', 'margin-left:5px; padding-left: 5px; border-left: 1px solid black;').append('a').attr('href', 'http://www.shortscience.org/paper?bibtexKey='+p.pid).html('review');
    var discuss_text = p.num_discussion === 0 ? 'discuss' : 'discuss [' + p.num_discussion + ']';
    var discuss_color = p.num_discussion === 0 ? 'black' : 'red';
    var review_span = ldiv.append('span').classed('sim', true).attr('style', 'margin-left:5px; padding-left: 5px; border-left: 1px solid black;')
                      .append('a').attr('href', 'notes?id='+strip_version(p.pid)).attr('style', 'color:'+discuss_color).html(discuss_text);
    ldiv.append('br');

    var lib_state_img = p.in_library === 1 ? 'static/saved.png' : 'static/save.png';
    var saveimg = ldiv.append('img').attr('src', lib_state_img)
                    .classed('save-icon', true)
                    .attr('title', 'toggle save paper to library (requires login)')
                    .attr('id', 'lib'+p.pid);
    // attach a handler for in-library toggle
    saveimg.on('click', function(pid, elt){
      return function() {
        if(username !== '') {
          // issue the post request to the server
          $.post("/libtoggle", {pid: pid})
           .done(function(data){
              // toggle state of the image to reflect the state of the server, as reported by response
              if(data === 'ON') {
                elt.attr('src', 'static/saved.png');
              } else if(data === 'OFF') {
                elt.attr('src', 'static/save.png');
              }
           });
        } else {
          alert('you must be logged in to save papers to library.')
        }
      }
    }(p.pid, saveimg)); // close over the pid and handle to the image

    div.append('div').attr('style', 'clear:both');

    if(typeof p.abstract !== 'undefined') {
      var abdiv = div.append('span').classed('tt', true).html(p.abstract);
      if(dynamic) {
        MathJax.Hub.Queue(["Typeset",MathJax.Hub,abdiv[0]]); //typeset the added paper
      }
    }

    // in friends tab, list users who the user follows who had these papers in libary
    if(render_format === 'friends') {
      if(pid_to_users.hasOwnProperty(p.rawpid)) {
        var usrtxt = pid_to_users[p.rawpid].join(', ');
        div.append('div').classed('inlibsof', true).html('In libraries of: ' + usrtxt);
      }
    }
    if ((p.twtr_links !== undefined) && (p.twtr_links.length > 0)) {
        var tweets_div_id = `tweets-${ix}`;
        var toggle_button = div.append('div').append('button');
        toggle_button.text('Show tweets').attr('target', '#' + tweets_div_id).on('click', function() {
            $($(this).attr('target')).toggle();
        });
        var tdiv = div.append('div').classed('twdiv', true).attr('id', tweets_div_id);
        p.twtr_links.map( function (t, idx) {
            var cur_d = tdiv.append('div');
            cur_d.append('span').classed('tweet-meta', true).html(`<i class="far fa-heart"></i> ${t.likes} &nbsp; <i class="fas fa-retweet"></i> ${t.rt} &nbsp; <i class="fas fa-reply"></i> ${t.replies || 0} &nbsp; &nbsp; `);
            cur_d.append('a').attr('href', 'https://twitter.com/' + t.tname + '/status/' + t.tid).attr('target', '_blank').text(`${t.name || t.tname}`);
        })
    }


    if(render_format == 'paper' && ix === 0) {
      // lets insert a divider/message
      div.append('div').classed('paperdivider', true).html('Most similar papers:');
    }
  }

  return pointer_ix >= papers.length; // are we done?
}

function timeConverter(UNIX_timestamp){
  var a = new Date(UNIX_timestamp * 1000);
  var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var year = a.getFullYear();
  var month = months[a.getMonth()];
  var date = a.getDate().toString();
  var hour = a.getHours().toString();
  var min = a.getMinutes().toString();
  var sec = a.getSeconds().toString();
  if(hour.length === 1) { hour = '0' + hour; }
  if(min.length === 1) { min = '0' + min; }
  if(sec.length === 1) { sec = '0' + sec; }
  var time = date + ' ' + month + ' ' + year + ', ' + hour + ':' + min + ':' + sec ;
  return time;
}


// when page loads...
$(document).ready(function(){

	urlq = QueryString.q;

  // display message, if any
  if(msg !== '') { d3.select("#rtable").append('div').classed('msg', true).html(msg); }

  // add papers to #rtable
	var done = addPapers(10, false);
  if(done) { $("#loadmorebtn").hide(); }

  // set up inifinite scrolling for adding more papers
  $(window).on('scroll', function(){
    var scrollTop = $(document).scrollTop();
    var windowHeight = $(window).height();
    var bodyHeight = $(document).height() - windowHeight;
    var scrollPercentage = (scrollTop / bodyHeight);
    if(scrollPercentage > 0.9) {
      var done = addPapers(5, true);
      if(done) { $("#loadmorebtn").hide(); }
    }
  });

  // just in case scrolling is broken somehow, provide a button handler explicit
  $("#loadmorebtn").on('click', function(){
    var done = addPapers(5, true);
    if(done) { $("#loadmorebtn").hide(); }
  });

  if(papers.length === 0) { $("#loadmorebtn").hide(); }

	if(!(typeof urlq == 'undefined')) {
		d3.select("#qfield").attr('value', urlq.replace(/\+/g, " "));
	}

  var vf = QueryString.vfilter; if(typeof vf === 'undefined') { vf = 'published'; }
  var tf = QueryString.timefilter; if(typeof tf === 'undefined') { tf = 'week'; }
  var link_endpoint = '/';
  if(render_format === 'recent') { link_endpoint = ''; }
  if(render_format === 'recommend') { link_endpoint = 'recommend'; }
  if(render_format === 'toptwtr') { link_endpoint = 'toptwtr'; }
  if(render_format === 'oldhype') { link_endpoint = 'oldhype'; }
  if(render_format === 'discussions') { link_endpoint = 'discussions'; }

  var time_ranges = ['day', '3days', 'week', '2weeks', 'month', 'year', 'alltime'];
  var time_txt = {'day':'Last day', '3days': 'Last 3 days', 'week': 'Last week', '2weeks': '2 weeks', 'month': 'Last month', 'year': 'Last year', 'alltime': 'All time'}
  var time_range = tf;

  // set up time filtering options
  if(render_format === 'recommend' || render_format === 'top' || render_format === 'recent' || render_format === 'friends') {
    // insert version filtering options for these views
    var elt = d3.select('#recommend-time-choice');
    var vflink = vf === 'published' ? 'last_updated' : 'published'; // toggle only showing v1 or not
    if(render_format === 'recent') {
      var aelt = elt.append('a').attr('href', '/'+link_endpoint+'?'+'&vfilter='+vflink); // leave out timefilter from this page
    } else {
      var aelt = elt.append('a').attr('href', '/'+link_endpoint+'?'+'timefilter='+time_range+'&vfilter='+vflink);
    }
    var delt = aelt.append('div').classed('vchoice', true).html('Sort by last update');
    if(vf === 'last_updated') { delt.classed('vchoice-selected', true); }
  }

  // time choices for recommend/top
  if(render_format === 'recommend' || render_format === 'top' || render_format === 'friends') {
    // insert time filtering options for these two views
    var elt = d3.select('#recommend-time-choice');
    elt.append('div').classed('fdivider', true).html('|');
    for(var i=0;i<time_ranges.length;i++) {
      var time_range = time_ranges[i];
      var aelt = elt.append('a').attr('href', '/'+link_endpoint+'?'+'timefilter='+time_range+'&vfilter='+vf);
      var delt = aelt.append('div').classed('timechoice', true).html(time_txt[time_range]);
      if(tf == time_range) { delt.classed('timechoice-selected', true); } // also render as chosen
    }
  }

  // time choices for top tweets
  if(render_format === 'toptwtr') {
    var tf = QueryString.timefilter; if(typeof tf === 'undefined') { tf = 'week'; } // default here is day
    var time_ranges = ['day', 'week', 'month'];
    var elt = d3.select('#recommend-time-choice');
    for(var i=0;i<time_ranges.length;i++) {
      var time_range = time_ranges[i];
      var aelt = elt.append('a').attr('href', '/'+link_endpoint+'?'+'timefilter='+time_range);
      var delt = aelt.append('div').classed('timechoice', true).html(time_txt[time_range]);
      if(tf == time_range) { delt.classed('timechoice-selected', true); } // also render as chosen
    }
    var decay_button = elt.append('div').classed('form-check', true);
    decay_button.html('<input type="checkbox" class="form-check-input" id="age_decay"><label class="form-check-label">Age Decay</label>')
    document.getElementById('age_decay').checked = (QueryString.age_decay === '1' ? true : false);
  }

  // time choices for top tweets
  if(render_format === 'oldhype') {
    var tf = QueryString.timefilter; if(typeof tf === 'undefined') { tf = 'week'; } // default here is day
    var time_ranges = ['day', 'week', '2weeks'];
    var elt = d3.select('#recommend-time-choice');
    for(var i=0;i<time_ranges.length;i++) {
      var time_range = time_ranges[i];
      var aelt = elt.append('a').attr('href', '/'+link_endpoint+'?'+'timefilter='+time_range);
      var delt = aelt.append('div').classed('timechoice', true).html(time_txt[time_range]);
      if(tf == time_range) { delt.classed('timechoice-selected', true); } // also render as chosen
    }
  }
  var xb = $("#xbanner");
  if(xb.length !== 0) {
    xb.click(function(){ $("#banner").slideUp('fast'); })
  }

  // in top tab: color current choice
  $('#pagebar .nav-link').removeClass('active');
  $(`.${render_format}`).addClass('active');
  $('#pagebar .dropdown-toggle').text($(`.${render_format}`)[0].text);


  $("#goaway").on('click', function(){
    $("#prompt").slideUp('fast');
    $.post("/goaway", {}).done(function(data){ });
  });

  $(document).on('change', '#age_decay', function(e) {
    window.location.href = updateQueryStringParameter(window.location.href, 'age_decay', this.checked ? '1' : '0');
  });

});
