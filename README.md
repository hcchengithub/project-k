
A FORTH programming language kernel
======================

# en

jeForth was first invented by Yap and Sam Suan Chen, FigTaiwan during 
end of 2011. It's a very simple way to develop your own FORTH system 
anywhere JavaScript is available -- Web page, HTA, Node.js, Node-Webkit 
or NW.js, and Windows DOS box, to name only those have tested so far.  

This project has only one file, `projectk.js`, which reduces the original jeForth 
down to having only two FORTH 
words, "`code`" and "`end-code`", and a few other JavaScript 
global functions like `push()`, `pop()`, `tos()`, `tick()`, and `last()`, etc. 
The benefit is that, having JavaScript host behind, we don't need to build 
an entire FORTH system to do just a little thing in FORTH way. 

**New!** Python version is now available too. Thanks to the jupyter notebook and the 
binder technology we can use project-k online to start building your own system. 
Play it now if you have 15 minutes: [https://mybinder.org/v2/gh/hcchengithub/project-k/master?filepath=Play%20with%20the%20FORTH%20kernel%20on%20jupyter%20notebook.ipynb](
https://mybinder.org/v2/gh/hcchengithub/project-k/master?filepath=Play%20with%20the%20FORTH%20kernel%20on%20jupyter%20notebook.ipynb)

See also https://github.com/hcchengithub/peforth which is a developped python FORTH top on project-k.


# play now

Click one of the following links to play demo directly from the GitHub 
repository through the amazing service of "rawgit.com",

**baby.html**<br>
* baby.html : http://rawgit.com/hcchengithub/project-k/master/baby.html
* baby.html (cdn): http://cdn.rawgit.com/hcchengithub/project-k/master/baby.html

**sample.html**<br>
* sample.html : http://rawgit.com/hcchengithub/project-k/master/sample.html
* sample.html (cdn): http://cdn.rawgit.com/hcchengithub/project-k/master/sample.html

Try one or the other, cdn may be necessary at where you are.
Demo **baby.html** is very simple and its FORTH source code area is very short 
too, so please try to read them; while **sample.html** has most FORTH words 
already. Try 'words' command and 'see' their definitions. Read messages 
on the screen and try what it says. As shown below,

![enter image description here](https://github.com/hcchengithub/project-k/wiki/pictures/run-project-k-example.jpg)

Microsoft Windows' browser (IE or Edge) may block the demo program, as shown in 
the above screen capture, you need to enable something. Better use Google Chrome 
to avoid the little obstacle.

# hands on


projectk.js is the only file in this project. The below two lines generate a FORTH Virtual Machine on your web page in HTML:

    <script src="./projectk.js"></script>
    <script> vm = new jeForth(); </script>

Now we have an object 'vm' which is the FORTH virtual machine that has only two FORTH words 'coce' and 'end-code'. Use the two words to create your own entire FORTH system then. 

# tutorials and documents
Find tutorials and documents in [the wiki](https://github.com/hcchengithub/project-k/wiki).

# quick reference

On variant applications, how to get the project-k VM up and running,

**a.** For HTML and HTA:

    <script src="http://hcchengithub.github.io/project-k/projectk.js"></script>
    <script> vm = new jeForth(); </script>

**b.** For Node.js and Node-webkit:

    jeForth = require("./projectk.js").jeForth;
    vm = new jeForth();

**c.** For WSH cscript.exe:

    eval(readTextFile(".\\projectk.js"));
    vm = new jeForth();
    /* readTextFile() is not cscript.exe built-in, you need to write it */

# real thing
[jeforth.3we](http://github.com/hcchengithub/jeforth.3we) is this project's 
predecessor that has completely been developed. You can use it to do real 
things. The bast way to learn FORTH is to create your own FORTH. So I 
rejuvenate jeforth.3we back to it's kernel, the projectk.js source code, for 
people to develop their own FORTH system from a higher starting point.

# participation

Any suggestion or question, use the 'issues' and 'wiki' on this GitHub 
repository, raise them to [the FigTaiwan forum](https://groups.google.com/forum/?hl=zh-TW#!forum/figtaiwan) 
or email me. 

# tw
整理 FigTaiwan 用 JavaScript 寫成的 Forth VM, 只專注在 kernel 
使它能適用所有的場合（HTML, Node.js, Node-webkit, WSH, HTA）。
這個目的迫使 kernel 必須精簡、易懂。說明稿直接放在 GitHub > project-k > Wiki，
透過 GitHub > project-k > issues 追蹤討論單項問題。

***
### Happy programming !
FigTaiwan H.C. Chen<br>
hcchen5600@gmail.com<br>
