project-k
========

整理 FigTaiwan 用 JavaScript 寫成的 Forth VM, 只專注在 kernel.js 使它能在所有的 application （HTML, Node.js, Node-webkit, WSH, HTA, 等）通用。這會使得 kernel.js 更精簡、易懂。即使如此，由版權的選擇、到結構的設計、到每一項命名，皆需廣徵意見。

本稿直接放在 GitHub > project-k > Wiki 供參與者編輯。也可以透過 GitHub > project-k > issues 追蹤討論單項問題。

講解當前草案
=============

 - 檔案
 - 如何 include kernel.js
 - 以 Node.js 空手直接使用 kernel.js 
 - kernel.js 裡的組成部位

檔案
------

 1. kernel.js （將來唯一實存的檔案，無以名之，直稱 kernel）
 2. kernel.f （僅供參考）
 3. quit.f （無形，或僅供建議）

如何 include kernel.js [（video）](http://www.camdemy.com/media/19528)
-----------------------------

kernel.js 提供的是一個 Forth VM 的 constructor. 暫且沿用 Yap 先生原創，名為 KsanaVM(). 以下例舉使用 KsanaVM() 生成 kvm 的幾種方式。其中 kvm 即本 Forth VM 的 instance. 可視需要任意命名，但注意 instance 的取名當然會牽動整套 application. 

請多批評、請指點是否有別的方式需要考慮進來。

**a.** For HTML, HTA, and Node-webkit:

    <script src="./kernel.js"></script>
    <script> window.kvm = new KsanaVM(); </script>

**b.** For Node.js and Node-webkit:

    global.KsanaVM = require("./kernel.js").KsanaVM;
    global.kvm = new KsanaVM();

**c.** For WSH:

    eval(readTextFile(".\\kernel.js"));
    kvm = new KsanaVM();

以 Node.js 空手直接使用 kernel.js [（video）](http://www.camdemy.com/media/19529)
--------------------------------------------------

這很好玩，您不必熟悉 JavaScript。藉由手動操作，做一遍就應該對本 project 會有很清楚的認識。

(1). 以 Node.js 為例, Just run it:

    node.exe
    
(2). Do the [above **b.**](http://www.camdemy.com/media/19528) to create **kvm** under the Node.js console.

(3). Define **type()** for the specific application. For Node.js text console in this example case:

    kvm.type = function (s) { 
	    try {
            var ss = s + '';
        } catch(err) {
            var ss = Object.prototype.toString.apply(s);
        }
        process.stdout.write(ss);
    }

(4). Test kvm.type('abc')

(5). Play around with kvm properties and methods

    kvm.init()
    kvm.dictate("123")
    kvm.stack()
    kvm.dictate("code hi type('Hello World!!') end-code")
    kvm.dictate("hi")
    kvm.words
    kvm.dictionary

kernel.js 裡的組成部位 （video）
---------------------------------

 1. Exported properties and methods
 2. VM internal global variables
 3. VM internal global methods

###Exported properties and methods

vm.init() 串接唯一的 I/O。"vm" 是 KsanaVM 內部參考自身的 reference. 若 instance 是 foo = new KsanaVM() 則 foo 就是 vm。 

	vm.init = function () { 
		type = vm.type;
	}

vm.dictate() 是唯一對外的「聽令者」，因為有 context save-restore 所以「聽令者」都是獨立的個體。只要所下命令留有 idle time 給 JavaScript host 就可以同時 dictate 不只一組命令讓 KsanaVM multi-tasking。

	// Recursively evaluate the input. 
	// The input can be multiple lines or an entire ~.f file but
	// it usually is the TIB.
	function dictate(input) {
		var tibwas=tib, ntibwas=ntib, ipwas=ip;
		tib = input; 
		ntib = 0;
		stop = false; // stop 是給 outer loop 看的，這裡要先清除。
		outer();
		tib = tibwas;
		ntib = ntibwas;
		ip = ipwas;
	}
	vm.dictate = dictate;

Data stack 常被操弄，用 reference 會錯所以要用 function 直接傳回元身。Return stack 也跟著比照辦理:

	vm.stack = function(){return(stack)};
	vm.rstack = function(){return(rstack)};

words 的結構是 words["vocabulary"]["word-name"] 所有的 Forth word 都在 words 之下；dictionary 是單純的 array。這兩個 vm property 都不會被操弄，直接以原形 export:

	vm.words = words;
	vm.dictionary = dictionary;

###VM internal global variables

希望這些 variables 都能設計到令人一望即知無需解釋。 (video)

	var vm = this;
	var ip=0;
	var stack = [] ;
	var rstack = [];
	var vocs = [];
	var words = [];
	var current = "forth";
	var context = "forth";
	var order = [context];
	var wordhash = {};
	var dictionary=[]; dictionary[0]=0;
	var here=1;
	var tib="";
	var ntib=0;
	var RET=null; // The 'ret' instruction code. It marks the end of a colon word.
	var EXIT=""; // The 'exit' instruction code.
	var compiling=false;
	var stop = false; // Stop the outer loop
	var newname = ""; // new word's name
	var newxt = function(){}; // new word's function()
	var newhelp = ""; // new word's help
	var type = function(){}; // The only I/O, dummy at first.
	var g = {}; // global hash

###VM internal global functions

這是最後一段了，本 project 真的沒有多少東西。希望這些 function 都能令人一望即知不需要太多解釋。 (video)

	type("s") 
	nextstring("delimitor") 
	nexttoken("delimitor")
	mytypeof(x)
	panic("msg", boolean:severe) and jsc
	isReDef("name")
	reset(void) 
	Word(a[])

以下都是傳統 Forth 本有的 function 盡量都以 Forth 習見的 word name 命名： (video)

	last(void)
	current_word_list(void)
	context_word_list(void)
	tick("name")
	comma(x)
	execute(x)
	inner (entry, boolean:resuming)
	outer(entry)
	dictate("input")
	tos(index,data)
	rtos(index,data)
	pop(index)
	push(data,index)


> Written with [StackEdit](https://stackedit.io/).

