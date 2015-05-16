A minimized jeForth kernel
==========================
#en
A very simple way to develop your own Forth system on Web page, HTA, Node.js, Node-Webkit, Windows DOS box, and anywhere JavaScript is available. jeforth.js is the only file in this project. The below two lines is a demo to use it to generate a Forth VM on your web page in HTML:

    <script src="./jeforth.js"></script>
    <script> window.vm = new jeForth(); </script>

Now we have an object 'vm' which is the Forth virtual machine that has only two initial Forth words 'coce' and 'end-code'. Use the two words to create your own entire Forth system then. 

#demo
baby.html is a simple complete demo. Use Google Chrome to run it.

#how to include 

**a.** For HTML, HTA, and Node-webkit:

    <script src="./jeforth.js"></script>
    <script> window.vm = new jeForth(); </script>

**b.** For Node.js and Node-webkit:

    global.vm = require("./jeforth.js").jeForth;
    global.vm = new jeForth();

**c.** For WSH:

    eval(readTextFile(".\\jeforth.js"));
    vm = new jeForth();

jeForth was first invented by FigTaiwan Mr. Yap and Sam Suan Chen during end of 2011. Any suggestion or question, use the 'issues' and 'wiki' on this GitHub repository or email me at hcchen5600@gmail.com. 

Happy programming !

#tw
整理 FigTaiwan 用 JavaScript 寫成的 Forth VM, 只專注在 kernel 使它能在所有的 application （HTML, Node.js, Node-webkit, WSH, HTA）通用。這會使得 kernel 更精簡、易懂。說明稿直接放在 GitHub > project-k > Wiki 供參與者編輯。也可以透過 GitHub > project-k > issues 追蹤討論單項問題。


> Written with [StackEdit](https://stackedit.io/).

