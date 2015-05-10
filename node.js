
// 
// Usage: node.exe node.js cr .' Hello World!!' cr bye
//

global.jeForth = require('./jeforth.js').jeForth;
global.kvm = new jeForth();
global.kvm.g = {};
var type = kvm.type = function (s) { 
			try {
				var ss = s + ''; // Print-able test to avoid error 'JavaScript error on word "." : invalid data'
			} catch(err) {
				var ss = Object.prototype.toString.apply(s);
			}
			process.stdout.write(ss);
		}; 
kvm.clearScreen = function(){console.log('\033c')} // '\033c' or '\033[2J' http://stackoverflow.com/questions/9006988/node-js-on-windows-how-to-clear-console
kvm.fso = require('fs');
kvm.readTextFile = function(pathname){return(kvm.fso.readFileSync(pathname,'utf-8'))}
kvm.writeTextFile = function(pathname,data){kvm.fso.writeFileSync(pathname,data,'utf8')}
kvm.bye = function(n){process.exit(n)}
kvm.prompt = "OK";

// There's no main loop, event driven call back function is this.
kvm.forthConsoleHandler = function(cmd) {
	var rlwas = kvm.rstack().length; // r)stack l)ength was
	kvm.dictate(cmd);
	(function retry(){
		// rstack 平衡表示這次 command line 都完成了，這才打 'OK'。
		// event handler 從 idle 上手，又回到 idle 不會讓別人看到它的 rstack。
		// 雖然未 OK, 仍然可以 key in 新的 command line 且立即執行。
		if(kvm.rstack().length!=rlwas)
			setTimeout(retry,100); 
		else {
			type(" " + kvm.prompt + " ");
		}
	})();
}
 
kvm.stdio = require('readline').createInterface({input: process.stdin,output: process.stdout});
kvm.stdio.on('line', kvm.forthConsoleHandler);
kvm.stdio.setPrompt(' '+kvm.prompt+' ',4);
kvm.init();
kvm.dictate(kvm.fso.readFileSync('jeforth.f','utf-8'));
// dictate() 之後不能再有任何東西，否則因為有 sleep/suspend/resume 之故，會被意外執行到。

