
A Forth programming language kernel in JavaScript
======================

# en

jeForth was first invented by FigTaiwan Mr. Yap and Sam Suan Chen during end of 2011. It's a very simple way to develop your own Forth system anywhere JavaScript is available -- Web page, HTA, Node.js, Node-Webkit or NW.js, and Windows DOS box, tested so far.  

This project has only one file : projectk.js, which provides two Forth words : "code" and "end-code" and a few other Forth related JavaScript global functions like push(), pop(), tos(), tick(), and last(), etc. The benefit is that, having JavaScript host behind, we don't need to build an entire Forth system, as some may think so, to do just a little things. 

# play now

Click one of the following links to play demo directly from the GitHub repository through the amazing service of "rawgit.com",

* baby.html : http://rawgit.com/hcchengithub/project-k/master/baby.html
* baby.html (cdn): http://cdn.rawgit.com/hcchengithub/project-k/master/baby.html
* sample.html : http://rawgit.com/hcchengithub/project-k/master/sample.html
* sample.html (cdn): http://cdn.rawgit.com/hcchengithub/project-k/master/sample.html

Demo **baby.html** is very simple and its forth source code area is very short too, so please try to read them; while **sample.html** has most forth words already. Try 'words' command and 'see' their definitions. Anyway, read messages on the screen and try what it says. As shown below,

![enter image description here](https://github.com/hcchengithub/project-k/wiki/pictures/run-project-k-example.jpg)

Microsoft Windows' browser (IE or Edge) may block the demo program, see the above screen capture, you need to enable something. Better use Google Chrome to avoid the little obstacle.

# hands on


projectk.js is the only file in this project. The below two lines generate a Forth Virtual Machine on your web page in HTML:

    <script src="./projectk.js"></script>
    <script> vm = new jeForth(); </script>

Now we have an object 'vm' which is the Forth virtual machine that has only two Forth words 'coce' and 'end-code'. Use the two words to create your own entire Forth system then. 

# tutorials and documents
Find tutorials and documents in [the wiki](https://github.com/hcchengithub/project-k/wiki).

# quick reference

Get the jeforth VM up and running on variant environments,

**a.** For HTML and HTA:

    <script src="./projectk.js"></script>
    <script> vm = new jeForth(); </script>

**b.** For Node.js and Node-webkit:

    jeForth = require("./projectk.js").jeForth;
    vm = new jeForth();

**c.** For WSH cscript.exe:

    eval(readTextFile(".\\projectk.js"));
    vm = new jeForth();
    /* readTextFile() is not cscript.exe built-in, you need to write it */

# real thing
[jeforth.3we](http://github.com/hcchengithub/jeforth.3we) is this project's predecessor that has completely developed. You can use it to do real things. The bast way to learn Forth is to create your own Forth. So I rejuvenate jeforth.3we back to it's kernel, the projectk.js source code, for people to develop their own Forth system from a higher starting point.

# participation

Any suggestion or question, use the 'issues' and 'wiki' on this GitHub repository, raise them to [the FigTaiwan forum](https://groups.google.com/forum/?hl=zh-TW#!forum/figtaiwan) or email me at hcchen5600@gmail.com. 

# tw
整理 FigTaiwan 用 JavaScript 寫成的 Forth VM, 只專注在 kernel 使它能適用所有的場合（HTML, Node.js, Node-webkit, WSH, HTA）。這個目的迫使 kernel 必須精簡、易懂。說明稿直接放在 GitHub > project-k > Wiki，透過 GitHub > project-k > issues 追蹤討論單項問題。

***
### Happy programming !
FigTaiwan H.C. Chen
hcchen5600@gmail.com
